#!/usr/bin/env python
#
# glvector_funcs.py - Functions used by glrgbvector_funcs and
#                     gllinevector_funcs.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module contains logic for managing vertex and fragment shader programs
used for rendering :class:`.GLRGBVector` and :class:`.GLLineVector` instances.
These functions are used by the :mod:`.gl14.glrgbvector_funcs` and
:mod:`.gl14.gllinevector_funcs` modules.
"""


import fsleyes.gl.shaders  as shaders
import fsl.utils.transform as transform


def destroy(self):
    """Destroys the vertex/fragment shader programs created in :func:`init`.
    """
    self.shader.destroy()
    self.shader = None

    
def compileShaders(self, vertShader):
    """Compiles the vertex/fragment shader programs (by creating a
    :class:`.GLSLShader` instance).

    If the :attr:`.VectorOpts.colourImage` property is set, the ``glvolume``
    fragment shader is used. Otherwise, the ``glvector`` fragment shader
    is used.
    """
    if self.shader is not None:
        self.shader.destroy()

    opts                = self.displayOpts
    useVolumeFragShader = opts.colourImage is not None

    if useVolumeFragShader: fragShader = 'glvolume'
    else:                   fragShader = 'glvector'
    
    vertSrc  = shaders.getVertexShader(  vertShader)
    fragSrc  = shaders.getFragmentShader(fragShader)

    if useVolumeFragShader:
        textures = {
            'clipTexture'      : 1,
            'imageTexture'     : 2,
            'colourTexture'    : 3,
            'negColourTexture' : 3
        }

    else:
        textures = {
            'modulateTexture' : 0,
            'clipTexture'     : 1,
            'vectorTexture'   : 4, 
        } 
        
    self.shader = shaders.ARBPShader(vertSrc, fragSrc, textures)


def updateFragmentShaderState(self):
    """Updates the state of the fragment shader - it may be either the
    ``glvolume`` or the ``glvector`` shader.
    """
    
    opts                = self.displayOpts
    useVolumeFragShader = opts.colourImage is not None 
    shape               = list(self.vectorImage.shape[:3])
    modLow,  modHigh    = self.getModulateRange()
    clipLow, clipHigh   = self.getClippingRange() 

    clipping = [clipLow, clipHigh,                 -1, -1]
    mod      = [modLow,  1.0 / (modHigh - modLow), -1, -1]

    self.shader.load()

    # Inputs which are required by both the
    # glvolume and glvetor fragment shaders
    self.shader.setFragParam('imageShape', shape + [0])
    self.shader.setFragParam('clipping',   clipping)
    
    if useVolumeFragShader:
        
        voxValXform    = self.colourTexture.voxValXform
        invVoxValXform = self.colourTexture.voxValXform
        cmapXform      = self.cmapTexture.getCoordinateTransform()
        voxValXform    = transform.concat(voxValXform, cmapXform)
        texZero        = 0.0 * invVoxValXform[0, 0] + invVoxValXform[3, 0]
        
        self.shader.setFragParam('voxValXform', voxValXform)
        self.shader.setFragParam('negCmap',     [0, texZero, 0, 0])

    else:

        voxValXform          = self.imageTexture.voxValXform
        colours, colourXform = self.getVectorColours()
         
        self.shader.setFragParam('voxValXform', voxValXform)
        self.shader.setFragParam('mod',         mod)
        self.shader.setFragParam('xColour',     colours[0])
        self.shader.setFragParam('yColour',     colours[1])
        self.shader.setFragParam('zColour',     colours[2])
        self.shader.setFragParam('colourXform', [colourXform[0, 0],
                                                 colourXform[3, 0], 0, 0])

    self.shader.unload()

    return True
