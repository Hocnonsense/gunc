#!/usr/bin/env python3
import os
import sys
import glob
import json
import argparse
import pandas as pd
from . import gunc_database
from . import external_tools
from . import visualisation as vis
from .get_scores import chim_score
from ._version import get_versions
from .external_tools import get_record_count_in_fasta as record_count


def parse_args(args):
    """Parse Arguments

    Arguments:
        args (List): List of args supplied to script.

    Returns:
        Namespace: assigned args

    """
    description = ('Tool for detection of chimerism and '
                   'contamination in prokaryotic genomes.\n')
    parser = argparse.ArgumentParser(description=description)
    subparsers = parser.add_subparsers(title='GUNC subcommands',
                                       metavar='',
                                       dest='cmd')
    run = subparsers.add_parser('run',
                                help='Run chimerism detection.')
    run_group = run.add_mutually_exclusive_group(required=True)
    download_db = subparsers.add_parser('download_db',
                                        help='Download GUNC db.')
    vis = subparsers.add_parser('plot',
                                help='Create interactive visualisation.',
                                formatter_class=lambda prog:
                                    argparse.ArgumentDefaultsHelpFormatter(prog,
                                                                           max_help_position=100))

    run.add_argument('-r', '--db_file',
                     help='DiamondDB reference file. Default: GUNC_DB envvar',
                     default=os.environ.get('GUNC_DB'),
                     metavar='')
    run_group.add_argument('-i', '--input_fna',
                           help='Input file in FASTA fna format.',
                           metavar='')
    run_group.add_argument('-f', '--input_file',
                           help='File with paths to files in FASTA fna format.',
                           metavar='')
    run_group.add_argument('-d', '--input_dir',
                           help='Input dir with files in FASTA fna format.',
                           metavar='')
    run.add_argument('-e', '--file_suffix',
                     help='Suffix of files in input_dir. Default: .fa',
                     default='.fa',
                     metavar='')
    run_group.add_argument('-g', '--gene_calls',
                           help='Input genecalls FASTA faa format.',
                           metavar='')
    run.add_argument('-p', '--threads',
                     help='number of CPU threads. Default: 4',
                     default='4',
                     metavar='')
    run.add_argument('-t', '--temp_dir',
                     help='Directory to store temp files. Default: cwd',
                     default=os.getcwd(),
                     metavar='')
    run.add_argument('-o', '--out_dir',
                     help='Output dir.  Default: cwd',
                     default=os.getcwd(),
                     metavar='')
    run.add_argument('-s', '--sensitive',
                     help='Run with high sensitivity. Default: False',
                     action='store_true',
                     default=False)
    run.add_argument('-b', '--detailed_output',
                     help='Output scores for every taxlevel. Default: False',
                     action='store_true',
                     default=False)
    vis.add_argument('-d', '--diamond_file',
                     help='GUNC diamond outputfile.',
                     required=True,
                     metavar='')
    vis.add_argument('-g', '--gunc_gene_count_file',
                     help='GUNC gene_counts.json file.',
                     metavar='')
    vis.add_argument('-o', '--out_dir',
                     help='Output directory.',
                     default=os.getcwd(),
                     metavar='')
    vis.add_argument('-t', '--tax_levels',
                     help='Tax levels to display (comma-seperated).',
                     default='kingdom,phylum,family,genus,contig',
                     metavar='')
    vis.add_argument('-r', '--remove_minor_clade_level',
                     help='Tax level at which to remove minor clades.',
                     default='kingdom',
                     metavar='')
    vis.add_argument('-c', '--contig_display_num',
                     help='Numper of contigs to visualise.',
                     default=1000,
                     type=int,
                     metavar='')
    download_db.add_argument('path',
                             help='Download database to given direcory.',
                             metavar='dest_path')
    parser.add_argument('-v', '--version',
                        help='Print version number and exit.',
                        action='version',
                        version=get_versions()['version'])
    if not args:
        parser.print_help(sys.stderr)
        sys.exit()
    args = parser.parse_args(args)
    return args


def create_dir(path):
    """Create a directory

    Will create a directory if it doesnt already exist.

    Arguments:
        path (str): directory path
    """
    if not os.path.exists(path):
        os.makedirs(path)


def start_checks():
    """Checks if tool dependencies are available."""
    if not external_tools.check_if_tool_exists('diamond'):
        sys.exit('[ERROR] Diamond 2.0.4 not found..')
    else:
        diamond_ver = external_tools.check_diamond_version()
        if diamond_ver != '2.0.4':
            sys.exit(f'[ERROR] Diamond version is {diamond_ver}, not 2.0.4')
    if not external_tools.check_if_tool_exists('prodigal'):
        sys.exit('[ERROR] Prodigal not found..')
    if not external_tools.check_if_tool_exists('zgrep'):
        sys.exit('[ERROR] zgrep not found..')


def get_files_in_dir_with_suffix(directory, suffix):
    """Get files in directory that end in suffix."""
    files = glob.glob(os.path.join(directory, f'*{suffix}'))
    if len(files) == 0:
        sys.exit(f'[ERROR] No files found in {directory} with ending {suffix}')
    return files


def merge_genecalls(genecall_files, out_dir):
    """Merge genecall files.

    Merges fastas together to run diamond more efficiently.
    Adds the name of the file to each record (delimiter '_-_')
    so they can be separated after diamond mapping.

    Arguments:
        genecall_files (list): Paths of genecall fastas to merge
        out_dir (str): Directory to put the merged file

    Returns:
        str: path of the merged file
    """
    merged_outfile = os.path.join(out_dir, 'merged.genecalls.faa')
    with open(merged_outfile, 'w') as ofile:
        for file in genecall_files:
            with open(file, 'r') as infile:
                genome_name = os.path.basename(file).replace('.genecalls.faa',
                                                             '')
                for line in infile:
                    if line.startswith('>'):
                        contig_name = line.split(' ')[0]
                        line = f'{contig_name}_-_{genome_name}\n'
                    ofile.write(line)
    return merged_outfile


def split_diamond_output(diamond_outfile, out_dir):
    """Split diamond output into per-sample files.

    Separate diamond output file into the constituent sample files.
    This uses the identifiers that were added by :func:`merge_genecalls`

    Arguments:
        diamond_outfile (str): path to the diamond file to be split
        out_dir (str): Directory in which to put the split files.

    Returns:
        list: Of the split file paths
    """
    outfiles = []
    output = {}
    with open(diamond_outfile, 'r') as f:
        for line in f:
            genome_name = line.split('\t')[0].split('_-_')[1]
            line = line.replace(f'_-_{genome_name}', '')
            output[genome_name] = output.get(genome_name, '') + line
    for genome_name in output:
        outfile = os.path.join(out_dir, f'{genome_name}.diamond.out')
        outfiles.append(outfile)
        with open(outfile, 'w') as ofile:
            ofile.write(output[genome_name])
    return outfiles


def write_json(data, filename):
    """Write json data to filename."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


def get_paths_from_file(input_file):
    """Extract paths from a text file."""
    with open(input_file, 'r') as f:
        paths = f.readlines()
    return [path.strip() for path in paths]


def run_from_gene_calls(gene_calls):
    """Get genecalls and genecount from gene fasta."""
    input_basename = os.path.basename(gene_calls)
    genes_called = {input_basename: record_count(gene_calls)}
    return genes_called, gene_calls


def run_from_fnas(fnas, out_dir, file_suffix):
    """Call genes and prepare diamond input.

    Args:
        fnas (list): Of fasta files
        out_dir (str): Directory in which to put genecalls
        file_suffix (str): Suffix of input files

    Returns:
        tuple:
            - genes_called (dict): {input_file: gene count}
            - diamond_inputfile (str): merged input file for diamond

    """
    create_dir(out_dir)
    genecall_files = []
    genes_called = {}
    for i, fna in enumerate(fnas):
        print(f'[INFO] Running Prodigal {i}/{len(fnas)}', flush=True)
        basename = os.path.basename(fna).split(file_suffix)[0]
        prodigal_outfile = os.path.join(out_dir, f'{basename}.genecalls.faa')
        external_tools.prodigal(fna, prodigal_outfile)
        genes_called[basename] = record_count(prodigal_outfile)
        genecall_files.append(prodigal_outfile)
    diamond_inputfile = merge_genecalls(genecall_files, out_dir)
    return genes_called, diamond_inputfile


def run_diamond(infile, threads, temp_dir, db_file, out_dir):
    """Rundiamong and split ouput.

    Runs diamond on infile and if needed splits the constitiuent samples.

    Args:
        infile (str): Path to gene calls fasta to run diamond on.
        threads (int): Number of threads to use for diamond.
        temp_dir (str): Path of tempdir for diamond running.
        db_file (str): Path to diamond database file (GUNC_DB).
        out_dir (str): Path of directory in which to put the output files.

    Returns:
        list: Of diamond output files.
    """
    outfile = os.path.join(out_dir, f'{os.path.basename(infile)}.diamond.out')
    external_tools.diamond(infile, threads, temp_dir, db_file, outfile)

    if infile.endswith('merged.genecalls.faa'):
        out_dir = os.path.join(out_dir, 'diamond_output')
        create_dir(out_dir)
        diamond_outfiles = split_diamond_output(outfile, out_dir)
        os.remove(outfile)
        os.remove(infile)
    else:
        diamond_outfiles = [outfile]
    return diamond_outfiles


def run_gunc(diamond_outfiles, genes_called, out_dir, sensitive, detailed_output):
    """Call GUNC scores on diamond output files.

    Outputs a pandas.DataFrame with one line per inputfile
    (taxlevel with highest CSS score).
    If detailed_output = True, files with all taxlevels are written.

    Args:
        diamond_outfiles (list): Paths of diamond output files.
        genes_called (dict): filename: genecount.
        out_dir (str): Path to output directory.
        sensitive (bool): Run with high sensitivity.
        detailed_output (bool): Output scores for every taxlevel.

    Returns:
        pandas.DataFrame: One line per inputfile Gunc scores
    """
    gunc_output = pd.DataFrame()
    for diamond_file in diamond_outfiles:
        basename = os.path.basename(diamond_file).replace('.diamond.out', '')
        print(f'[INFO] Calculating GUNC scores for {basename}:')
        gene_call_count = genes_called[basename]
        detailed, single = chim_score(diamond_file, gene_call_count, sensitive)
        if detailed_output:
            detailed_gunc_out_dir = os.path.join(out_dir, 'gunc_output')
            detailed_gunc_out_file = os.path.join(detailed_gunc_out_dir,
                                                  f'{basename}.chimerism_scores')
            create_dir(detailed_gunc_out_dir)
            detailed.to_csv(detailed_gunc_out_file, index=False, sep='\t')
        return gunc_output.append(single, sort=False)


def run(args):
    """Run entire GUNC workflow."""
    if args.input_dir:
        fnas = get_files_in_dir_with_suffix(args.input_dir, args.file_suffix)
    elif args.input_file:
        fnas = get_paths_from_file(args.input_file)
    elif args.input_fna:
        fnas = [args.input_fna]

    if args.gene_calls:
        gene_calls_out_dir = args.out_dir
        genes_called, diamond_input = run_from_gene_calls(args.gene_calls)
    else:
        gene_calls_out_dir = os.path.join(args.out_dir, 'gene_calls')
        genes_called, diamond_input = run_from_fnas(fnas,
                                                    gene_calls_out_dir,
                                                    args.file_suffix)

    genes_called_outfile = os.path.join(gene_calls_out_dir, 'gene_counts.json')
    write_json(genes_called, genes_called_outfile)

    diamond_outfiles = run_diamond(diamond_input, args.threads,
                                   args.temp_dir, args.db_file, args.out_dir)

    gunc_output = run_gunc(diamond_outfiles, genes_called, args.out_dir,
                           args.sensitive, args.detailed_output)
    gunc_out_file = os.path.join(args.out_dir, 'gunc_scores.tsv')
    gunc_output.to_csv(gunc_out_file, index=False, sep='\t')


def get_gene_count_file(args):
    """Search for gunc gencount file."""
    if not args.gunc_gene_count_file:
        diamond_file_path = os.path.abspath(args.diamond_file)
        gunc_dir = os.path.dirname(os.path.dirname(diamond_file_path))
        gene_counts_file = os.path.join(gunc_dir,
                                        "gene_calls/gene_counts.json")
        if not os.path.isfile(gene_counts_file):
            sys.exit('[ERROR] GUNC gene_counts.json file not found!')
    else:
        gene_counts_file = args.gunc_gene_count_file


def get_genecount_from_gunc_output(gene_counts_file, basename):
    """Extract gene count from GUNC gene_counts.json file."""
    with open(gene_counts_file) as f:
        data = json.load(f)
    return int(data[basename])


def plot(args):
    """Run visualisation function."""
    basename = os.path.basename(args.diamond_file).replace('.diamond.out', '')
    genes_called = get_genecount_from_gunc_output(get_gene_count_file(args),
                                                  basename)
    viz_html = vis.create_viz_from_diamond_file(args.diamond_file,
                                                genes_called,
                                                args.tax_levels,
                                                args.contig_display_num,
                                                args.remove_minor_clade_level)
    viz_html_path = os.path.join(args.out_dir, f'{basename}.viz.html')
    with open(viz_html_path, 'w') as f:
        f.write(viz_html)


def main():
    args = parse_args(sys.argv[1:])
    if args.cmd == 'download_db':
        gunc_database.get_db(args.path)
    if args.cmd == 'run':
        start_checks()
        if not args.db_file:
            sys.exit('[WARNING] database_file argument missing.')
        run(args)
    if args.cmd == 'plot':
        plot(args)


if __name__ == "__main__":
    main()
