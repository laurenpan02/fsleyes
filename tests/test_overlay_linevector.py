#!/usr/bin/env python
#
# test_overlay_linevector.py -
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#

import pytest

from . import run_cli_tests, roi, ndvec, asrgb


pytestmark = pytest.mark.overlayclitest


cli_tests = """
# Test line width
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -lw 1
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -lw 5
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -lw 10

# Test line length scaling
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -nu
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector     -ls  500
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -nu -ls  500
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector     -ls  500 -lw 5
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -nu -ls  500 -lw 5

# Test directed vectors
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -ld
dti/dti_FA.nii.gz dti/dti_V1.nii.gz -ot linevector -ld -ls 500 -lw 3

# Test 1D/2D  vector images
{{roi('dti/dti_V1', (0, 8, 4, 5, 4, 5))}} -ot linevector
{{roi('dti/dti_V1', (0, 8, 0, 8, 4, 5))}} -ot linevector

# test RGB images
                                  dti/dti_FA.nii.gz {{asrgb('dti/dti_V1.nii.gz')}}           -ot linevector
-vl 0 0 0 -xc 0 0 -yc 0 0 -zc 0 0 dti/dti_FA.nii.gz {{asrgb(ndvec('dti/dti_V1.nii.gz', 1))}} -ot linevector
-vl 0 0 0 -xc 0 0 -yc 0 0 -zc 0 0 dti/dti_FA.nii.gz {{asrgb(ndvec('dti/dti_V1.nii.gz', 2))}} -ot linevector
"""


def test_overlay_linevector():
    extras = {
        'roi'   : roi,
        'asrgb' : asrgb,
        'ndvec' : ndvec,
    }
    run_cli_tests('test_overlay_linevector', cli_tests, extras=extras)
