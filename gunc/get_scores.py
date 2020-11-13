#!/usr/bin/env python3
import os
import sys
import argparse
import scipy
import numpy as np
import pandas as pd
from sklearn import metrics
from collections import OrderedDict
from pkg_resources import resource_filename


def parse_args(args):
    """Parse Arguments

    Arguments:
        args (list): list of args supplied to script.

    Returns:
        (Namespace): assigned args

    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--diamond_file_path',
                        help='diamond output',
                        required=True,
                        default=False)
    parser.add_argument('-z', '--dry_run',
                        help='Dont change anything but print commands instead',
                        action='store_true',
                        default=False)
    parser.add_argument('-s', '--sensitive',
                        help='Run with high sensitivity',
                        action='store_true',
                        default=False)
    args = parser.parse_args()
    return args


def read_diamond_output(file_path):
    """Read in Diamond output.

    Args:
        file_path (Str): Full path to diamond output.

    Returns:
        DataFrame: Pandas df with diamond output.
    """
    df = pd.read_csv(file_path,
                     sep='\t',
                     header=None,
                     usecols=[0, 1, 2],
                     names=['query', 'genome', 'id'])
    if len(df) == 0:
        sys.exit('[ERROR] input data produced no alignments to reference.')
    else:
        df['contig'] = df['query'].str.rpartition('_')[[0]]
        return df


def get_n_effective_surplus_clades(counts):
    """Calculate Simpson Index.

    Inverse Simpson Index of all clade labels distribution
    -1 (as 1 genome is expected)

    Arguments:
        counts (list): Counts of taxons in a taxlevel.

    Returns:
        float: Score describing the extent of chimerism.
    """

    denom = sum(counts) ** 2
    return 1 / sum([x ** 2 / denom for x in counts]) - 1


def calc_completeness_score(contigs, taxons):
    """Get completeness score.

    Completeness metric of a cluster labeling given a ground truth.
    Score of 1.0 stands for perfectly complete labeling.

    Args:
        contigs ([str]): labels_true
        taxons ([str]): labels_pred

    Returns:
        float: score between 0.0 and 1.0.
    """
    return metrics.completeness_score(contigs, taxons)


def expected_entropy_estimate(probabilities, sample_count):
    """Compute the expected entropy estimate sampling N elements underlying
    probabilities `p`


    Arguments:
        probabilities (array): probabilities (p) (assumed to sum to 1.0)
        sample_count (int): number of samples (N)

    Returns
        entropy (float): expected entropy
    """
    entropy = 0.0
    for probability in probabilities:
        sample_array = np.arange(1, sample_count)
        entropy += np.sum(scipy.special.comb(sample_count, sample_array)
                          * np.power(probability, sample_array)
                          * np.power(1 - probability,
                                     sample_count - sample_array)
                          # should be sample_array/sample_count
                          # but we moved the 1/sample_count out:
                          * sample_array
                          * np.log(sample_array / sample_count))
    return -entropy / sample_count


def calc_expected_clade_separation_score(contigs, taxons):
    """Compute the expected CSS under the null hypothesis that there is no
    influence

    When the bucket is large enough, the estimates are expected to be close
    enough to the global estimate that we will no longer compute the estimate
    via the more costly `expected_entropy_estimate` function

    Arguments:
        contigs (Series): contig names in data
        taxons (Series): taxons in data

    Returns:
        float: expected completeness score
    """

    MAX_BUCKET_SIZE = 500
    counts = taxons.value_counts()
    taxon_entropy = scipy.stats.entropy(counts.values)
    if taxon_entropy == 0:
        return 0.0

    bucket_sizes = contigs.value_counts().value_counts()
    nr_elements = (bucket_sizes * bucket_sizes.index)
    contribution = nr_elements / nr_elements.sum()

    taxon_probability = counts / counts.sum()
    taxon_probability = taxon_probability.values

    total_entropy = 0.0
    for bucket_size, contig_count in contribution.iteritems():
        if bucket_size <= MAX_BUCKET_SIZE:
            total_entropy += (contig_count
                              * expected_entropy_estimate(taxon_probability,
                                                          bucket_size))
        else:
            total_entropy += contig_count * taxon_entropy

    return 1 - total_entropy / taxon_entropy


def read_genome2taxonomy_reference():
    """Read in genome2taxonomy reference data.

    This file translates the genomes in the diamond reference file to taxonomy.

    Returns:
        DataFrame: Pandas dataframe
    """
    genome2taxonomy = resource_filename(__name__,
                                        'data/genome2taxonomy_ref.tsv')
    return pd.read_csv(genome2taxonomy, sep='\t')


def create_base_data(diamond_df):
    """Assign taxonomies to diamond output.

    Arguments:
        diamond_df (DataFrame): diamond output

    Returns:
        DataFrame: merged dataframe
    """
    genome2taxonomy_df = read_genome2taxonomy_reference()
    return pd.merge(diamond_df, genome2taxonomy_df, on='genome', how="inner")


def get_stats(diamond_df):
    """Get summary statistics of diamond output.

    Arguments:
        diamond_df (DataFrame): pandas dataframe

    Returns:
        tuple: number of genes mapped, number of contigs
    """
    genes_mapped = len(diamond_df)
    contig_count = diamond_df['contig'].nunique()
    return (genes_mapped, contig_count)


def get_abundant_lineages_cutoff(sensitive, genes_mapped):
    """Determine cutoff for abundant lineages.

    [description]

    Arguments:
        sensitive (bool): sets cutoff to 10 if true
        genes_mapped (int): total number of genes mapped by diamond to the GUNC DB

    Returns:
        number: cutoff used to determine an abundant lineage
    """
    if sensitive:
        return 10
    else:
        return 0.02 * genes_mapped


def calc_contamination_portion(counts):
    """Calculate contamination portion

    Arguments:
        counts (Series): Value counts of taxons in taxlevel

    Returns:
        float: portion of genes assigning to all clades except the one with most genes.
    """
    return 1 - counts.max() / counts.sum()


def mean(list_of_numbers):
    """Get mean of a list of numbers.

    Arguments:
        list_of_numbers (list): numbers to get mean of

    Returns:
        float: mean of numbers
    """
    return sum(list_of_numbers) / len(list_of_numbers)


def calc_mean_hit_identity(identity_scores):
    """Calculate mean hit identity score.

    TODO: get info from askarbek

    Arguments:
        identity_scores (list): list of identity scores

    Returns:
        float: Score
    """
    return mean(identity_scores) / 100


def column_to_list(df, column):
    """Geta a list of values for a df column.

    Convert one column from a pandas DataFrame
    and return it as a list.

    Arguments:
        df (DataFrame): df containing column to convert
        column (str): name of column to extract

    Returns:
        list: Column values as list
    """
    return df[column].to_list()


def calc_clade_separation_score(contamination_portion, completeness_score):
    """Get clade separation score.

    TODO: get info from askarbek

    Arguments:
        contamination_portion (float): [description]
        completeness_score (float): [description]

    Returns:
        number: [description]
    """
    if contamination_portion == 0:
        return 0
    else:
        return completeness_score


def determine_adjustment(clade_separation_score, mean_clade_separation_score,
                         genes_retained_index):
    """Determine if adjustment is necessary.

    TODO: get info from askarbek

    Arguments:
        clade_separation_score ([type]): [description]
        mean_clade_separation_score ([type]): [description]
        genes_retained_index ([type]): [description]

    Returns:
        number: [description]
    """
    if clade_separation_score > (mean_clade_separation_score + 0.1):
        if genes_retained_index > 0.4:
            return 1
    return 0


def is_chimeric(clade_separation_score_adjusted):
    """Determine if chimeric.

    TODO: Why .4

    Arguments:
        clade_separation_score_adjusted (float): score

    Returns:
        bool: is genome chimeric
    """
    if clade_separation_score_adjusted > 0.4:
        return True
    else:
        return False


def get_scores_for_taxlevel(base_data, tax_level, abundant_lineages_cutoff,
                            genome_name, genes_called, genes_mapped,
                            contig_count):
    """Run chimerism check.

    Calculates the various scores needed to determine if genome ic chimeric.

    Arguments:
        base_data (DataFrame): Diamond output merged with taxonomy table
        tax_level (str): tax level to run
        abundant_lineages_cutoff (float): Cutoff val for abundant lineages
        genome_name (str): Name of input genome
        genes_called (int): Number of genes called by prodigal and
                            used by diamond for mapping to GUNC DB
        genes_mapped (int): Number of genes mapped to GUNC DB by diamond
        contig_count (int): Count of contigs

    Returns:
        OrderedDict: scores for chosen taxlevel
    """
    tax_data = base_data.groupby(tax_level).filter(
        lambda x: len(x) > abundant_lineages_cutoff)
    counts = tax_data[tax_level].value_counts()
    contigs = column_to_list(tax_data, 'contig')
    taxons = column_to_list(tax_data, tax_level)

    n_effective_surplus_clades = get_n_effective_surplus_clades(counts)
    contamination_portion = calc_contamination_portion(counts)
    mean_hit_identity = calc_mean_hit_identity(column_to_list(tax_data,
                                                              'id'))
    completeness_score = calc_completeness_score(contigs, taxons)
    portion_genes_retained = len(tax_data) / genes_mapped
    mean_clade_separation_score = calc_expected_clade_separation_score(tax_data['contig'],
                                                                       tax_data[tax_level])
    genes_retained_index = genes_mapped / genes_called * portion_genes_retained
    clade_separation_score = calc_clade_separation_score(contamination_portion,
                                                         completeness_score)
    reference_representation_score = genes_retained_index * mean_hit_identity
    adjustment = determine_adjustment(clade_separation_score,
                                      mean_clade_separation_score,
                                      genes_retained_index)
    clade_separation_score_adjusted = clade_separation_score * adjustment
    chimeric = is_chimeric(clade_separation_score_adjusted)
    return OrderedDict({'genome': genome_name,
                        'n_contigs': contig_count,
                        'n_genes_called': genes_called,
                        'n_genes_mapped': genes_mapped,
                        'taxonomic_level': tax_level,
                        'clade_separation_score': clade_separation_score,
                        'contamination_portion': contamination_portion,
                        'n_effective_surplus_clades': n_effective_surplus_clades,
                        'proportion_genes_retained_in_major_clades': portion_genes_retained,
                        'mean_hit_identity': mean_hit_identity,
                        'mean_random_clade_separation_score': mean_clade_separation_score,
                        'genes_retained_index': genes_retained_index,
                        'reference_representation_score': reference_representation_score,
                        'adjustment': adjustment,
                        'clade_separation_score_adjusted': clade_separation_score_adjusted,
                        'chimeric': chimeric})


def chim_score(diamond_file_path, genes_called=0, sensitive=False, plot=False):
    """Get chimerism scores for a genome.

    Arguments:
        diamond_file_path (str): Full path to diamond output

    Keyword Arguments:
        genes_called (int): Count of genes called by prodigal and used by
                            diamond for mapping into the GUNC DB (default: ('0'))
        sensitive (bool): Run in sensitive mode (default: (False))
    """
    genes_called = int(genes_called)
    if genes_called < 10:
        sys.exit('[WARNING] Less than 10 genes called, exiting...')

    diamond_df = read_diamond_output(diamond_file_path)
    base_data = create_base_data(diamond_df)
    genes_mapped, contig_count = get_stats(diamond_df)

    genome_name = os.path.basename(diamond_file_path).replace('.diamond.out', '')
    abundant_lineages_cutoff = get_abundant_lineages_cutoff(sensitive,
                                                            genes_mapped)
    if plot:
        return base_data, genome_name, abundant_lineages_cutoff

    scores = []
    for tax_level in ['kingdom', 'phylum', 'class',
                      'order', 'family', 'genus', 'specI']:
        print(tax_level)
        scores.append(get_scores_for_taxlevel(base_data,
                                              tax_level,
                                              abundant_lineages_cutoff,
                                              genome_name,
                                              genes_called,
                                              genes_mapped,
                                              contig_count))
    df = pd.DataFrame(scores).round(2)
    return df


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    df = chim_score(args.diamond_file_path, args.sensitive)
    df.to_csv(f'{args.diamond_file_path}.chimerism_scores',
              index=False,
              sep='\t')
