# -*- coding: utf-8 -*-
"""Entrypoint for biomedsheets

The biomedsheets package provides Python library modules as well as an
executable for the various
"""

import argparse
import collections
import json
import logging
import os
import pkg_resources
import sys

from .io import SheetSchema, json_loads_ordered, SheetBuilder
from .ref_resolver import RefResolver
from .validation import SchemaValidator
from .shortcuts import (
    SHEET_TYPES, RARE_DISEASE, CANCER_MATCHED, GENERIC_EXPERIMENT)
from . import xlsx_sheets

__author__ = 'Manuel Holtgrewe <manuel.holtgrewe@bihealth.de>'


class AppBase:
    """Base class for application, sub classed for each command"""

    def __init__(self, args):
        #: Parsed command line arguments
        self.args = args


class SheetAppBase(AppBase):
    """Base class for working with sheets"""

    def __init__(self, args):
        super().__init__(args)
        #: SheetSchema from bundled json
        self.sheet_schema = self.load_sheet_schema()
        #: Validator for BioMed JSON schemas
        self.validator = SchemaValidator(self.sheet_schema)
        #: Sample sheet JSON
        self.sheet_json = self.load_sheet_json()
        #: Resolved JSON
        self.resolved_json = self.resolve_refs(self.sheet_json)

    def run(self):
        """Execute the command"""
        raise NotImplementedError('Abstract method called: override me!')

    def load_sheet_schema(self):
        """Load the bundled SheetSchema"""
        print('Loading bundled BioMed Sheet JSON Schema...', file=sys.stderr)
        return SheetSchema.load_from_string(pkg_resources.resource_stream(
            'biomedsheets', 'data/sheet.schema.json').read().decode())

    def load_sheet_json(self):
        """Load the sheet JSON file"""
        print('Loading sheet JSON from "{}"'.format(self.args.input),
              file=sys.stderr)
        try:
            with open(self.args.input, 'rt') as f:
                return json_loads_ordered(f.read())
        except FileNotFoundError as e:
            raise  # re-raise

    def get_lib_dirs(self):
        """Return list of paths to search for relative paths"""
        lib_dirs = list(self.args.lib_dir)
        lib_dirs.append(os.path.dirname(os.path.abspath(self.args.input)))
        return lib_dirs

    def resolve_refs(self, sheet_json):
        """Resolve "$ref" JSON pointers in sheet_json"""
        print('Resolving {{ "$ref": "..." }} in JSON...')
        resolver = RefResolver(
            lookup_paths=self.get_lib_dirs(),
            dict_class=collections.OrderedDict)
        return resolver.resolve('file://' + self.args.input, sheet_json)

    def validate_and_print_errors(self):
        errors = self.validator.validate(self.resolved_json)
        if errors:
            print('The following validation errors occured', file=sys.stderr)
            for error in errors:
                print(' - {}'.format(error), file=sys.stderr)
        return errors

class ValidateApp(SheetAppBase):
    """App sub class for validation sub command"""

    def run(self):
        if self.validate_and_print_errors():
            return 1
        else:
            print('Sheet passed validation, congratulation!', file=sys.stderr)


class ExpandApp(SheetAppBase):
    """App sub class for expanding "$ref" JSON pointers"""

    def run(self):
        json.dump(self.resolved_json, self.args.output, indent='  ')
        print('', file=self.args.output)


class JSONToXLSXApp(SheetAppBase):
    """App sub class for converting JSON to XLSX sheet"""

    def run(self):
        # Check whether JSON data is valid and break from function otherwise
        if self.validate_and_print_errors():
            return 1
        # Build models.Sheet from JSON and write out to XLSX
        print('Building BioMed Sheet...', file=sys.stderr)
        sheet = SheetBuilder(self.resolved_json).run()
        print('Write sheet to XLSX...', file=sys.stderr)
        writer = xlsx_sheets.SheetWriter(sheet)
        writer.write(self.args.output)


class XLSXToJSONApp(SheetAppBase):
    """App sub class for filling XLSX into a JSON sheet (write to another
    JSON output sheet)
    """

    def run(self):
        # Check whether JSON data is valid and break from function otherwise
        if self.validate_and_print_errors():
            return 1
        # Build models.Sheet from JSON for the overall structure
        print('Building BioMed Sheet...', file=sys.stderr)
        tpl_sheet = SheetBuilder(self.resolved_json).run()
        # Load XLSX file, using sheet for type definitions etc., and write
        # out sheet again
        print('Loading sheet from XLSX file...', file=sys.stderr)
        sheet = xlsx_sheets.SheetLoader(tpl_sheet).load(self.input_xlsx)
        print('Write sheet to XLSX...', file=sys.stderr)
        writer = xlsx_sheets.SheetWriter(sheet)
        writer.write(self.args.output)


class XLSXCreateApp(AppBase):
    """App sub class for fresh creation of Excel sample sheet"""

    def run(self):
        CREATORS = {
            RARE_DISEASE: xlsx_sheets.RareDisaseSheetCreator,
            CANCER_MATCHED: xlsx_sheets.CancerMatchedSheetCreator,
            GENERIC_EXPERIMENT: xlsx_sheets.GenericExperimentSheetCreator,
        }
        return CREATORS[self.args.experiment_type]().run(self.args.output)


def run(args):
    """Program entry point after parsing command line arguments"""
    APPS = {
        'validate': ValidateApp,
        'expand': ExpandApp,
        'xlsx-create': XLSXCreateApp,
        'json-xlsx': JSONToXLSXApp,
        'xlsx-json': XLSXToJSONApp,
    }
    return APPS[args.subparser](args).run()


def main(argv=None):
    """Main program entry point, starts parsing command line arguments"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--lib-dir', type=str, default=['.', os.getcwd()], action='append',
        help=('Base directorie for JSON file pointers, can be given '
              'multiple times'))

    subparsers = parser.add_subparsers(dest='subparser')

    parser_validate = subparsers.add_parser(
        'validate', help='Validate sample sheet JSON')
    parser_validate.add_argument(
        '-i', '--input', type=str, required=True,
        help='Path to BioMed Sheet (JSON or YAML) file')

    parser_expand = subparsers.add_parser(
        'expand', help='Expand "$ref" JSON pointers')
    parser_expand.add_argument(
        '-i', '--input', type=str, required=True,
        help='Path to BioMed Sheet (JSON or YAML) file')
    parser_expand.add_argument(
        '-o', '--output', type=argparse.FileType('wt'), default=sys.stdout,
        help='Path to output file, defaults to stdout')

    parser_xlsx_create = subparsers.add_parser(
        'xlsx-create', help='Create XLSX sheet for schema')
    parser_xlsx_create.add_argument(
        '-t', '--experiment-type', type=str, choices=SHEET_TYPES,
        required=True, help='Type of XLSX sheet to created')
    parser_xlsx_create.add_argument(
        '-o', '--output', type=str, required=True,
        help='Path to XLSX sheet to create')

    parser_json_xlsx = subparsers.add_parser(
        'json-xlsx', help='Create XLSX from JSON schema')
    parser_json_xlsx.add_argument(
        '-i', '--input', type=str, required=True,
        help='Path to BioMed Sheet (JSON or YAML) file')
    parser_json_xlsx.add_argument(
        '-o', '--output', type=str, required=True,
        help='Path to XLSX sheet to create')

    parser_xlsx_json = subparsers.add_parser(
        'xlsx-json',
        help=('Write data from XLSX in structure given by one JSON file '
              'into another JSON file'))
    parser_xlsx_json.add_argument(
        '-i', '--input', type=str, required=True,
        help='Path to BioMed Sheet (JSON or YAML) file')
    parser_xlsx_json.add_argument(
        '-x', '--input-xlsx', type=str, required=True,
        help=('Path to BioMed Sheet XLSX file created by "xlsx-create" '
              'command'))
    parser_xlsx_json.add_argument(
        '-o', '--output', type=str, required=True,
        help='Path to JSON sheet to write to')

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

    args = parser.parse_args(argv)
    if not args.subparser:
        parser.print_usage()
        return 1
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
