# -*- coding: utf-8 -*
"""Python classes for enabling shortcut views on the biomedical sheet

Note that these shortcuts rely on the following assumptions.  These
assumptions are quite strong but make sense in clinical context.  Also, they
enforce a sensible streamlining of the high-throughput biomedical assay
structure which is the case for the interesting studies anyway.

- each shortcut sheet only uses one data type (e.g., WES, WGS, or mass-spec
  data)
- in the case of rare disease studies, only the first active bio and test
  sample and NGS library need to be considered
- in the case of cancer studies, only the first active test sample and NGS
  library are of interesting
- both one and multiple test samples can be of study, e.g., in the case
  of considering multiple parts of a larger tumor or metastesis
- the Decorator pattern is used for giving shortcut-based access to the sample
  sheet members

This all is to facilitate the automatic processing in pipelines.  Of course,
more assays can be combined by loading the results in a downstream step.
These downstream steps can then combine the information in any fashion they
see fit and build larger, more complex systems out of the simpler building
blocks that this module is meant for.

Also note that none of the shortcut objects will reflect changes in the
underlying schema data structure.
"""

# TODO: merge with generic?

from .. import models
from .. import NAME_PATTERN

__author__ = 'Manuel Holtgrewe <manuel.holtgrewe@bihealth.de>'

#: Token for identifying a rare disease sequencing experiment
RARE_DISEASE = 'rare_disease'
#: Token for identifying a cancer matched tumor/normal study
CANCER_MATCHED = 'cancer_matched'
#: Token for identifying a generic experiment
GENERIC_EXPERIMENT = 'generic_experiment'
#: Known sheet types with shortcuts
SHEET_TYPES = (RARE_DISEASE, CANCER_MATCHED, GENERIC_EXPERIMENT)

#: Extraction type "DNA"
EXTRACTION_TYPE_DNA = 'DNA'
#: Extraction type "RNA"
EXTRACTION_TYPE_RNA = 'RNA'


def is_background(sheet):
    """Return ``True`` if the ``Sheet`` shortcut is not flagged as background
    """
    return sheet.extra_infos.get('is_background', False)


def is_not_background(sheet):
    """Return ``True`` if the ``Sheet`` shortcut is not flagged as background
    """
    return not is_background(sheet)


class InvalidSelector(Exception):
    """Raised in the case of an invalid ``TestSample`` child type"""


class MissingDataEntity(Exception):
    """Raised if the given data entity is not known"""


class ShortcutSampleSheet:
    """Shortcut of a generic experiment sample sheet"""

    def __init__(self, sheet):
        #: The wrapped ``Sheet``
        self.sheet = sheet
        #: Shortcut to wrapped sheet
        self.wrapped = sheet
        #: A list of shortcut objects to all enabled NGS libraries
        self.all_ngs_libraries = None
        #: A list of shortcut objects to the first enabled NGS library for
        #: each sample
        self.primary_ngs_libraries = None

    @property
    def extra_infos(self):
        """Shorcut to wrapped object's ``extra_infos``"""
        return self.wrapped.extra_infos


class ShortcutMixin:
    """Mixin with helper functions"""

    @property
    def pk(self):
        """Shortcut to ``pk`` property of wrapped object

        The value is usually generated by data management system/database.
        """
        return self.wrapped.pk

    @property
    def secondary_id(self):
        """Shortcut to ``secondary_id`` property of wrapped object

        The value is usually assigned by the data generator/customer
        """
        return self.wrapped.secondary_id

    @property
    def name(self):
        """Generate name for donor, consisting of primary key and followed by
        "path" of secondary ids through sample sheet

        Name of the donor, generated by :py:ref:`NAME_PATTERN`
        """
        secondary_ids = []
        handle = self
        while handle is not None:
            secondary_ids.insert(0, handle.secondary_id)
            handle = handle.parent
        return NAME_PATTERN.format(
            pk=str(self.pk).rjust(6, '0'),
            secondary_id='-'.join(secondary_ids))

    @property
    def disabled(self):
        """Return whether the entry has been disabled"""
        return bool(self.wrapped.disabled)

    @property
    def enabled(self):
        """Return whether the entry has been enabled"""
        return not self.disabled

    @property
    def extra_infos(self):
        """Shorcut to wrapped object's ``extra_infos``"""
        return self.wrapped.extra_infos


class BioEntityShortcut:
    pass


class BioSampleShortcut(ShortcutMixin):
    """When navigating with the ``biomedsheets.shortcuts`` through the
    sheets, this is the type that you end up instead of raw ``TestSample``
    objects

    Objects of this class are pre-configured with a specific ``TestSample``
    child type (e.g., NGS library or MSProteinPool) where the primary
    active will be picked.
    """

    def __init__(self, bio_entity, bio_sample, selector):
        #: Containing shortcut to ``BioEntity``
        self.bio_entity = bio_entity
        #: Raw ``BioEntity``
        self.bio_sample = bio_sample
        #: Wrapped for Shortcut Mixin
        self.wrapped = bio_sample
        # Check selector for being valid
        if selector not in models.TEST_SAMPLE_CHILDREN:
            raise InvalidSelector(
                'Invalid test sample selector {}'.format(selector))
        #: Selector for ``TestSample`` children
        self.selector = selector
        #: The selected ``TestSample`` with the selected ``TestSample`` child
        self.test_sample = self._get_test_sample()
        #: The selected ``TestSample`` child
        self.assay_sample = self.test_sample.assay_sample

    def _get_test_sample(self):
        """Return appropriate ``TestSampleShortcut`` raise an exception"""
        values = {
            models.KEY_NGS_LIBRARY: lambda x: x.ngs_libraries.values(),
            models.KEY_MS_PROTEIN_POOL: lambda x: x.ms_protein_pools.values(),
        }
        for test_sample in self.bio_sample.test_samples.values():
            attr_lst = values.get(self.selector, lambda x: [])(test_sample)
            for entity in attr_lst:
                if not entity.disabled:
                    return TestSampleShortcut(self, test_sample, self.selector)
        raise MissingDataEntity(
            'Could not find data entity for type {} in {}'.format(
                self.selector, self.test_sample))

    def __repr__(self):
        return 'BioSampleShortcut({})'.format(', '.join(map(str, [
            self.bio_sample, self.selector, self.test_sample, self.assay_sample])))

    def __str__(self):
        return repr(self)


class TestSampleShortcut:
    """When navigating with the ``biomedsheets.shortcuts`` through the
    sheets, this is the type that you end up instead of raw ``TestSample``
    objects

    Objects of this class are pre-configured with a specific ``TestSample``
    child type (e.g., NGS library or MSProteinPool) where the primary
    active will be picked.
    """

    def __init__(self, bio_sample, test_sample, selector):
        #: Containing shortcut to ``BioSample``
        self.bio_sample = bio_sample
        #: Raw ``TestSample``
        self.test_sample = test_sample
        # Check selector for being valid
        if selector not in models.TEST_SAMPLE_CHILDREN:
            raise InvalidSelector(
                'Invalid test sample selector {}'.format(selector))
        #: Selector for ``TestSample`` children
        self.selector = selector
        #: The selected ``TestSample`` child
        self.assay_sample = self._get_assay_sample()

    @property
    def pk(self):
        """Shortcut to ``pk`` property of wrapped ``TestSample``

        The value is usually generated by data management system/database.
        """
        return self.test_sample.pk

    @property
    def secondary_id(self):
        """Shortcut to ``secondary_id`` property of wrapped ``TestSample``

        The value is usually assigned by the data generator/customer
        """
        return self.test_sample.secondary_id

    @property
    def name(self):
        """Generate name for test sample, consisting of primary key and
        followed by "path" of secondary ids through sample sheet

        Name of the donor, generated by "${pk}-${secondary_id}"
        """
        return NAME_PATTERN.format(
            pk=str(self.pk).rjust(6, '0'), secondary_id='-'.join([
                self.bio_sample.donor.secondary_id,
                self.bio_sample.secondary_id,
                self.secondary_id]))

    @property
    def disabled(self):
        """Shortcut to ``disabled`` property of wrapped ``TestSample``"""
        return self.test_sample.disabled

    @property
    def enabled(self):
        """Shortcut to ``enabled`` property of wrapped ``TestSample``"""
        return self.test_sample.enabled

    def _get_assay_sample(self):
        """Return ``TestSample`` child or raise an exception"""
        values = {
            models.KEY_NGS_LIBRARY: lambda x: x.ngs_libraries.values(),
            models.KEY_MS_PROTEIN_POOL: lambda x: x.ms_protein_pools.values(),
        }
        constructors = {
            models.KEY_NGS_LIBRARY: NGSLibraryShortcut,
            models.KEY_MS_PROTEIN_POOL: MSProteinPoolShortcut,
        }
        attr_lst = values.get(self.selector, lambda x: [])(self.test_sample)
        for entity in attr_lst:
            if not entity.disabled:
                return constructors[self.selector](self, entity)
        raise MissingDataEntity(
            'Could not find data entity for type {} in {}'.format(
                self.selector, self.test_sample))

    def __repr__(self):
        return 'TestSampleShortcut({})'.format(', '.join(map(str, [
            self.test_sample, self.selector, self.assay_sample])))

    def __str__(self):
        return repr(self)


class TestSampleChildShortcut:
    """Helper base class for children of ``TestSampleShortcut``
    """

    def __init__(self, test_sample, wrapped):
        #: Containing ``TestSampleChildShortcut``
        self.test_sample = test_sample
        #: Wrapped raw TestSample child
        self.wrapped = wrapped

    @property
    def pk(self):
        """Shortcut to ``pk`` property of wrapped ``TestSample``

        The value is usually generated by data management system/database.
        """
        return self.wrapped.pk

    @property
    def secondary_id(self):
        """Shortcut to ``secondary_id`` property of wrapped ``TestSample``

        The value is usually assigned by the data generator/customer
        """
        return self.wrapped.secondary_id

    @property
    def name(self):
        """Generate name for test sample, consisting of primary key and
        followed by "path" of secondary ids through sample sheet

        Name of the donor, generated by "${pk}-${secondary_id}"
        """
        return NAME_PATTERN.format(
            pk=str(self.pk).rjust(6, '0'), secondary_id='-'.join([
                self.test_sample.bio_sample.bio_entity.secondary_id,
                self.test_sample.bio_sample.secondary_id,
                self.test_sample.secondary_id,
                self.secondary_id]))

    @property
    def disabled(self):
        """Shortcut to ``disabled`` property of wrapped ``TestSample``"""
        return self.wrapped.disabled

    @property
    def enabled(self):
        """Shortcut to ``enabled`` property of wrapped ``TestSample``"""
        return self.wrapped.enabled

    @property
    def extra_infos(self):
        """Shorcut to wrapped object's ``extra_infos``"""
        return self.wrapped.extra_infos


class NGSLibraryShortcut(TestSampleChildShortcut):
    """Shortcut to NGSLibrary
    """

    def __init__(self, test_sample, ngs_library):
        super().__init__(test_sample, ngs_library)
        #: Wrapped raw ``NGSLibrary``
        self.ngs_library = ngs_library


class MSProteinPoolShortcut(TestSampleChildShortcut):
    """Shortcut to MSProteinPool
    """

    def __init__(self, test_sample, ms_protein_pool):
        super().__init__(test_sample, ms_protein_pool)
        #: Wrapped raw ``MSProteinPool``
        self.ms_protein_pool = ms_protein_pool


