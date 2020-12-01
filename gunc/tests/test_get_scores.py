import pytest
import numpy as np
import pandas as pd
from ..get_scores import *
from pkg_resources import resource_filename

diamond_output = resource_filename(__name__,
                                   'test_data/tiny_test.diamond.out')
diamond_df = read_diamond_output(diamond_output)
ref_base_data_path = resource_filename(__name__,
                                       'test_data/tiny_test.base_data')
ref_base_data = pd.read_csv(ref_base_data_path)


def test_parse_args():
    with pytest.raises(SystemExit):
        parse_args(['-h'])
    with pytest.raises(SystemExit):
        parse_args(['-f'])
    parser = parse_args(['-f', 'test_path'])
    assert parser.diamond_file_path == 'test_path'
    assert parser.sensitive == False


def test_read_diamond_output():
    empty_file = resource_filename(__name__, '__init__.py')
    with pytest.raises(SystemExit):
        read_diamond_output(empty_file)
    diamond_df = read_diamond_output(diamond_output)
    assert len(diamond_df) == 17
    assert len(diamond_df.columns) == 4


def test_get_n_effective_surplus_clades():
    assert get_n_effective_surplus_clades([1]) == 0
    assert get_n_effective_surplus_clades([2, 8, 1, 1, 3]) == pytest.approx(1.84,
                                                                            rel=1e-2)


def test_calc_expected_conditional_entropy():
    s = pd.Series
    assert calc_conditional_entropy(s([0, 0, 1, 1]), s([1, 1, 0, 0])) == 0
    assert calc_conditional_entropy(s([0, 0, 1, 1]), s([0, 1, 0, 1])) > 0.1


def test_create_base_data():
    new_base_data = create_base_data(diamond_df)
    pd.testing.assert_frame_equal(ref_base_data, new_base_data)


def test_get_stats():
    assert get_stats(diamond_df) == (17, 15)


def test_get_abundant_lineages_cutoff():
    assert get_abundant_lineages_cutoff(True, 3) == 10
    assert get_abundant_lineages_cutoff(False, 10) == 0.2


def test_calc_contamination_portion():
    counts = pd.Series({'a': 1, 'b': 2, 'c': 3, 'd': 4})
    assert calc_contamination_portion(counts) == 0.6


def test_mean():
    assert mean([1, 2, 3]) == 2
    assert mean([0]) == 0
    assert mean([1, 1, 1]) == 1


def test_calc_mean_hit_identity():
    assert calc_mean_hit_identity([1, 2, 3]) == 0.02


def test_is_chimeric():
    assert is_chimeric(0) is False
    assert is_chimeric(1) is True
    assert is_chimeric(0.39) is False
    assert is_chimeric(0.4) is False
    assert is_chimeric(0.41) is True


def test_get_scores_for_taxlevel():
    data = get_scores_for_taxlevel(ref_base_data,
                                   'kingdom',
                                   0.34,
                                   'test',
                                   35,
                                   17,
                                   15)
    assert data['genome'] == 'test'
    assert data['n_contigs'] == 15
    assert data['n_genes_called'] == 35
    assert data['n_genes_mapped'] == 17
    assert data['taxonomic_level'] == 'kingdom'
    assert data['clade_separation_score'] == 0
    assert data['contamination_portion'] == 0
    assert data['n_effective_surplus_clades'] == 0
    assert data['proportion_genes_retained_in_major_clades'] == 1
    assert round(data['mean_hit_identity'], 2) == 0.92
    assert round(data['genes_retained_index'], 2) == 0.49
    assert round(data['reference_representation_score'], 2) == 0.45
    assert data['adjustment'] == 1
    assert data['clade_separation_score_adjusted'] == 0
    assert data['chimeric'] is False

    data = get_scores_for_taxlevel(ref_base_data,
                                   'specI',
                                   0.34,
                                   'test',
                                   35,
                                   17,
                                   15)
    assert data['genome'] == 'test'
    assert data['n_contigs'] == 15
    assert data['n_genes_called'] == 35
    assert data['n_genes_mapped'] == 17
    assert data['taxonomic_level'] == 'specI'
    assert round(data['clade_separation_score'], 2) == 1
    assert round(data['contamination_portion'], 2) == 0.35
    assert round(data['n_effective_surplus_clades'], 2) == 1.28
    assert data['proportion_genes_retained_in_major_clades'] == 1
    assert round(data['mean_hit_identity'], 2) == 0.92
    assert round(data['genes_retained_index'], 2) == 0.49
    assert round(data['reference_representation_score'], 2) == 0.45
    assert data['adjustment'] == 1
    assert round(data['clade_separation_score_adjusted'], 2) == 1
    assert data['chimeric']

    data = get_scores_for_taxlevel(ref_base_data,
                                   'class',
                                   1000,
                                   'test',
                                   35,
                                   17,
                                   15)
    assert data['genome'] == 'test'
    assert data['n_contigs'] == 15
    assert data['n_genes_called'] == 35
    assert data['n_genes_mapped'] == 17
    assert data['taxonomic_level'] == 'class'
    np.testing.assert_equal(data['clade_separation_score'], np.nan)
    np.testing.assert_equal(data['contamination_portion'], np.nan)
    assert round(data['n_effective_surplus_clades'], 2) == 0
    assert data['proportion_genes_retained_in_major_clades'] == 0
    assert round(data['mean_hit_identity'], 2) == 0
    assert round(data['genes_retained_index'], 2) == 0
    assert round(data['reference_representation_score'], 2) == 0
    assert data['adjustment'] == 0
    np.testing.assert_equal(data['clade_separation_score_adjusted'], np.nan)
    np.testing.assert_equal(data['chimeric'], np.nan)


def test_chim_score():
    diamond_file_path = resource_filename(__name__,
                                          'test_data/test_genome.fa.diamond.out')
    data = chim_score(diamond_file_path, genes_called=1832)

    expected_data_path = resource_filename(__name__,
                                           'test_data/test_genome.fa.diamond.out.chimerism_scores')
    expected_data = pd.read_csv(expected_data_path, sep='\t')
    pd.testing.assert_frame_equal(data, expected_data)
