#!/usr/bin/env python3
import os
import sys
import configargparse
from . import gunc_database
from . import external_tools
from .get_scores import chim_score
from ._version import get_versions


def parse_args(args):
    """Parse Arguments

    Arguments:
        args {List} -- List of args supplied to script.

    Returns:
        {Namespace} -- assigned args

    """
    description = ('Tool for detection of chimerism and '
                   'contamination in prokaryotic genomes.\n')
    parser = configargparse.ArgumentParser(default_config_files=['~/.gunc'],
                                           description=description)
    group = parser.add_mutually_exclusive_group(required=True)

    parser.add_argument('-d', '--database_file',
                        help='Diamond database reference file.',
                        env_var='GUNC_DB',
                        metavar='')
    group.add_argument('-i', '--input_file',
                       help='Input file in FASTA fna format.',
                       metavar='')
    group.add_argument('-g', '--gene_calls',
                       help='Input genecalls FASTA faa format.',
                       metavar='')
    parser.add_argument('-p', '--threads',
                        help='number of CPU threads. Default: 4',
                        default='4',
                        metavar='')
    parser.add_argument('-t', '--temp_dir',
                        help='Directory to store temp files. Default: cwd',
                        default=os.getcwd(),
                        metavar='')
    parser.add_argument('-o', '--out_dir',
                        help='Output dir.  Default: cwd',
                        default=os.getcwd(),
                        metavar='')
    parser.add_argument('-s', '--sensitive',
                        help='Run with high sensitivity',
                        action='store_true',
                        default=False)
    parser.add_argument('-c', '--config',
                        help='Config file path',
                        is_config_file=True,
                        metavar='')
    group.add_argument('--download_db',
                       help='Download database to given direcory.',
                       metavar='')
    parser.add_argument('-v', '--version',
                        help='Print version number and exit.',
                        action='version',
                        version=get_versions()['version'])
    if not args:
        parser.print_help(sys.stderr)
        sys.exit()
    args = parser.parse_args()
    return args


def create_dir(path):
    """Create a directory

    Will create a directory if it doesnt already exist.

    Arguments:
        path {str} -- directory path
    """
    if not os.path.exists(path):
        os.makedirs(path)


def start_checks():
    """Checks if tool dependencies are available."""
    if not external_tools.check_if_tool_exists('diamond'):
        sys.exit('[ERROR] Diamond not found..')
    else:
        diamond_ver = external_tools.check_diamond_version()
        if diamond_ver != '2.0.4':
            sys.exit(f'[ERROR] Diamond version is {diamond_ver}, not 2.0.4')
    if not external_tools.check_if_tool_exists('prodigal'):
        sys.exit('[ERROR] Prodigal not found..')
    if not external_tools.check_if_tool_exists('zgrep'):
        sys.exit('[ERROR] zgrep not found..')


def main():
    args = parse_args(sys.argv[1:])
    if args.download_db:
        gunc_database.get_db(args.download_db)
        sys.exit()

    start_checks()

    if not args.database_file:
        sys.exit('[WARNING] database_file argument missing.')

    if args.input_file:
        input_basename = os.path.basename(args.input_file)
        prodigal_outfile = os.path.join(args.out_dir,
                                        f'{input_basename}.genecalls.faa')
        external_tools.prodigal(args.input_file, prodigal_outfile)
        diamond_inputfile = prodigal_outfile
    else:
        input_basename = os.path.basename(args.gene_calls)
        diamond_inputfile = args.gene_calls

    diamond_outfile = os.path.join(args.out_dir,
                                   f'{input_basename}.diamond.out')
    external_tools.diamond(diamond_inputfile,
                           args.threads,
                           args.temp_dir,
                           args.database_file,
                           diamond_outfile)
    gene_count = external_tools.get_record_count_in_fasta(diamond_inputfile)

    print('[INFO] Calculating scores for each tax-level:')
    df = chim_score(diamond_outfile, gene_count, args.sensitive)
    df.to_csv(f'{diamond_outfile}.chimerism_scores', index=False, sep='\t')


if __name__ == "__main__":
    main()
