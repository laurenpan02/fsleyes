#!/usr/bin/env python
#
# meshopts.py - The MeshOpts class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`MeshOpts` class, which defines settings
for displaying :class:`.Mesh` overlays.
"""


import logging

import numpy as np

import fsl.data.image       as fslimage
import fsl.utils.transform  as transform
import fsleyes_props        as props

import fsleyes.colourmaps   as colourmaps
import fsleyes.overlay      as fsloverlay
import fsleyes.colourmaps   as fslcmaps
from . import display       as fsldisplay
from . import colourmapopts as cmapopts


log = logging.getLogger(__name__)


def genMeshColour(overlay):
    """Called by :meth:`MeshOpts.__init__`. Generates an initial colour for
    the given :class:`.Mesh` overlay.

    If the overlay file name looks like it was generated by the FSL FIRST
    segmentation tool, returns a colour from the ``mgh-cma-freesurfer`` colour
    map. Otherwise returns a random colour.
    """
    filename        = str(overlay.dataSource)
    subcorticalCmap = colourmaps.getLookupTable('mgh-cma-freesurfer')

    if   'L_Thal' in filename: return subcorticalCmap.get(10).colour
    elif 'L_Caud' in filename: return subcorticalCmap.get(11).colour
    elif 'L_Puta' in filename: return subcorticalCmap.get(12).colour
    elif 'L_Pall' in filename: return subcorticalCmap.get(13).colour
    elif 'BrStem' in filename: return subcorticalCmap.get(16).colour
    elif 'L_Hipp' in filename: return subcorticalCmap.get(17).colour
    elif 'L_Amyg' in filename: return subcorticalCmap.get(18).colour
    elif 'L_Accu' in filename: return subcorticalCmap.get(26).colour
    elif 'R_Thal' in filename: return subcorticalCmap.get(49).colour
    elif 'R_Caud' in filename: return subcorticalCmap.get(50).colour
    elif 'R_Puta' in filename: return subcorticalCmap.get(51).colour
    elif 'R_Pall' in filename: return subcorticalCmap.get(52).colour
    elif 'R_Hipp' in filename: return subcorticalCmap.get(53).colour
    elif 'R_Amyg' in filename: return subcorticalCmap.get(54).colour
    elif 'R_Accu' in filename: return subcorticalCmap.get(58).colour

    return colourmaps.randomBrightColour()


class MeshOpts(cmapopts.ColourMapOpts, fsldisplay.DisplayOpts):
    """The ``MeshOpts`` class defines settings for displaying :class:`.Mesh`
    overlays. See also the :class:`.GiftiOpts` and :class:`.FreesurferOpts`
    sub-classes.
    """


    colour = props.Colour()
    """The mesh colour. """


    outline = props.Boolean(default=False)
    """If ``True``, an outline of the mesh is shown. Otherwise a
    cross- section of the mesh is filled.
    """


    outlineWidth = props.Real(minval=0.1, maxval=10, default=2, clamped=False)
    """If :attr:`outline` is ``True``, this property defines the width of the
    outline in pixels.
    """


    showName = props.Boolean(default=False)
    """If ``True``, the mesh name is shown alongside it.

    .. note:: Not implemented yet, and maybe never will be.
    """


    discardClipped = props.Boolean(default=False)
    """Flag which controls clipping. When the mesh is coloured according to
    some data (the :attr:`vertexData` property), vertices with a data value
    outside of the clipping range are either discarded (not drawn), or
    they are still drawn, but not according to the data, rather with the
    flat :attr:`colour`.
    """


    vertexData = props.Choice((None, ))
    """May be populated with the names of files which contain data associated
    with each vertex in the mesh, that can be used to colour the mesh. When
    some vertex data has been succsessfully loaded, it can be accessed via
    the :meth:`getVertexData` method.

    This property is not currently populated by the ``MeshOpts`` class, but
    is used by sub-classes (e.g. :class:`.GiftiOpts`).
    """


    vertexDataIndex = props.Int(minval=0, maxval=0, default=0, clamped=True)
    """If :attr:`vertexData` is loaded, and has multiple data points per
    vertex (e.g. time series), this property controls the index into the
    data.
    """


    refImage = props.Choice()
    """A reference :class:`.Image` instance which the mesh coordinates are
    in terms of.

    For example, if this :class:`.Mesh` represents the segmentation of
    a sub-cortical region from a T1 image, you would set the ``refImage`` to
    that T1 image.

    Any :class:`.Image` instance in the :class:`.OverlayList` may be chosen
    as the reference image.
    """


    useLut = props.Boolean(default=False)
    """If ``True``, and if some :attr:`vertexData` is loaded, the :attr:`lut`
    is used to colour vertex values instead of the :attr:`cmap` and
    :attr:`negativeCmap`.
    """


    lut = props.Choice()
    """If :attr:`useLut` is ``True``, a :class:`.LookupTable` is used to
    colour vertex data instead of the :attr:`cmap`/:attr:`negativeCmap`.
    """


    # This property is implicitly tightly-coupled to
    # the NiftiOpts.getTransform method - the choices
    # defined in this property are assumed to be valid
    # inputs to that method.
    coordSpace = props.Choice(('affine', 'pixdim', 'pixdim-flip', 'id'),
                              default='pixdim-flip')
    """If :attr:`refImage` is not ``None``, this property defines the
    reference image coordinate space in which the mesh coordinates are
    defined (i.e. voxels, scaled voxels, or world coordinates).

    =============== =========================================================
    ``affine``      The mesh coordinates are defined in the reference image
                    world coordinate system.

    ``id``          The mesh coordinates are defined in the reference image
                    voxel coordinate system.

    ``pixdim``      The mesh coordinates are defined in the reference image
                    voxel coordinate system, scaled by the voxel pixdims.

    ``pixdim-flip`` The mesh coordinates are defined in the reference image
                    voxel coordinate system, scaled by the voxel pixdims. If
                    the reference image transformation matrix has a positive
                    determinant, the X axis is flipped.
    =============== =========================================================

    The default value is ``pixdim-flip``, as this is the coordinate system
    used in the VTK sub-cortical segmentation model files output by FIRST.
    See also the :ref:`note on coordinate systems
    <volumeopts-coordinate-systems>`, and the :meth:`.NiftiOpts.getTransform`
    method.
    """


    wireframe = props.Boolean(default=False)
    """3D only. If ``True``, the mesh is rendered as a wireframe. """


    def __init__(self, overlay, *args, **kwargs):
        """Create a ``MeshOpts`` instance. All arguments are passed through
        to the :class:`.DisplayOpts` constructor.
        """

        # Set a default colour
        colour      = genMeshColour(overlay)
        self.colour = np.concatenate((colour, [1.0]))

        # ColourMapOpts.linkLowRanges defaults to
        # True, which is annoying for surfaces.
        self.linkLowRanges = False

        # A copy of the refImage property
        # value is kept here so, when it
        # changes, we can de-register from
        # the previous one.
        self.__oldRefImage = None

        # When the vertexData property is
        # changed, the data (and its min/max)
        # is loaded and stored in these
        # attributes. See the __vertexDataChanged
        # method.
        self.__vertexData      = None
        self.__vertexDataRange = None

        nounbind = kwargs.get('nounbind', [])
        nounbind.extend(['refImage', 'coordSpace', 'vertexData'])
        kwargs['nounbind'] = nounbind

        fsldisplay.DisplayOpts  .__init__(self, overlay, *args, **kwargs)
        cmapopts  .ColourMapOpts.__init__(self)

        # The master MeshOpts instance is just a
        # sync-slave, so we only need to register
        # property listeners on child instances
        self.__registered = self.getParent() is not None
        if self.__registered:

            self.overlayList.addListener('overlays',
                                         self.name,
                                         self.__overlayListChanged,
                                         immediate=True)

            self.addListener('refImage',
                             self.name,
                             self.__refImageChanged,
                             immediate=True)
            self.addListener('coordSpace',
                             self.name,
                             self.__coordSpaceChanged,
                             immediate=True)

            # We need to keep colour[3]
            # keeps colour[3] and Display.alpha
            # consistent w.r.t. each other (see
            # also MaskOpts)
            self.display.addListener('alpha',
                                     self.name,
                                     self.__alphaChanged,
                                     immediate=True)
            self        .addListener('colour',
                                     self.name,
                                     self.__colourChanged,
                                     immediate=True)

            self.addListener('vertexData',
                             self.name,
                             self.__vertexDataChanged,
                             immediate=True)

            self.__overlayListChanged()
            self.__updateBounds()

        # If we have inherited values from a
        # parent instance, make sure the vertex
        # data (if set) is initialised
        self.__vertexDataChanged()

        # If a reference image has not
        # been set on the parent MeshOpts
        # instance, see  if there is a
        # suitable one in the overlay list.
        if self.refImage is None:
            self.refImage = fsloverlay.findMeshReferenceImage(
                self.overlayList, self.overlay)


    def destroy(self):
        """Removes some property listeners, and calls the
        :meth:`.DisplayOpts.destroy` method.
        """

        if self.__registered:

            self.overlayList.removeListener('overlays', self.name)
            self.display    .removeListener('alpha',    self.name)
            self            .removeListener('colour',   self.name)

            for overlay in self.overlayList:

                # An error could be raised if the
                # DC has been/is being destroyed
                try:

                    display = self.displayCtx.getDisplay(overlay)
                    opts    = self.displayCtx.getOpts(   overlay)

                    display.removeListener('name', self.name)

                    if overlay is self.refImage:
                        opts.removeListener('transform', self.name)

                except:
                    pass

        self.__oldRefImage = None
        self.__vertexData  = None

        cmapopts  .ColourMapOpts.destroy(self)
        fsldisplay.DisplayOpts  .destroy(self)


    @classmethod
    def getVolumeProps(cls):
        """Overrides :meth:`DisplayOpts.getVolumeProps`. Returns a list
        of property names which control the displayed volume/timepoint.
        """
        return ['vertexDataIndex']


    def getDataRange(self):
        """Overrides the :meth:`.ColourMapOpts.getDisplayRange` method.
        Returns the display range of the currently selected
        :attr:`vertexData`, or ``(0, 1)`` if none is selected.
        """
        if self.__vertexDataRange is None: return (0, 1)
        else:                              return self.__vertexDataRange


    def getVertexData(self):
        """Returns the :attr:`.MeshOpts.vertexData`, if some is loaded.
        Returns ``None`` otherwise.
        """
        return self.__vertexData


    def vertexDataLen(self):
        """Returns the length (number of data points per vertex) of the
        currently selected :attr:`vertexData`, or ``0`` if no vertex data is
        selected.
        """

        if self.__vertexData is None:
            return 0

        elif len(self.__vertexData.shape) == 1:
            return 1

        else:
            return self.__vertexData.shape[1]


    def addVertexDataOptions(self, paths):
        """Adds the given sequence of paths as options to the
        :attr:`vertexData` property. It is assumed that the paths refer
        to valid vertex data files for the overlay associated with this
        ``MeshOpts`` instance.
        """

        vdataProp = self.getProp('vertexData')
        newPaths  = paths
        paths     = vdataProp.getChoices(instance=self)
        paths     = paths + [p for p in newPaths if p not in paths]

        vdataProp.setChoices(paths, instance=self)


    def getConstantColour(self):
        """Returns the current :attr::`colour`, adjusted according to the
        current :attr:`.Display.brightness`, :attr:`.Display.contrast`, and
        :attr:`.Display.alpha`.
        """

        display = self.display

        # Only apply bricon if there is no vertex data assigned
        if self.vertexData is None:
            brightness = display.brightness / 100.0
            contrast   = display.contrast   / 100.0
        else:
            brightness = 0.5
            contrast   = 0.5

        colour = list(fslcmaps.applyBricon(
            self.colour[:3], brightness, contrast))

        colour.append(display.alpha / 100.0)

        return colour


    @property
    def referenceImage(self):
        """Overrides :meth:`.DisplayOpts.referenceImage`.

        If a :attr:`refImage` is selected, it is returned. Otherwise,``None``
        is returned.
        """
        return self.refImage


    def getCoordSpaceTransform(self):
        """Returns a transformation matrix which can be used to transform
        the :class:`.Mesh` vertex coordinates into the display
        coordinate system.

        If no :attr:`refImage` is selected, this method returns an identity
        transformation.
        """

        if self.refImage is None or self.refImage not in self.overlayList:
            return np.eye(4)

        opts = self.displayCtx.getOpts(self.refImage)

        return opts.getTransform(self.coordSpace, opts.transform)


    def getVertex(self, xyz=None):
        """Returns an integer identifying the index of the mesh vertex that
        coresponds to the given ``xyz`` location,

        :arg xyz: Location to convert to a vertex index. If not provided, the
                  current :class:`.DisplayContext.location` is used.
        """

        # TODO return vertex closest to the point,
        #      within some configurabe tolerance?

        if xyz is None:
            xyz = self.displayCtx.location.xyz
            xyz = self.transformCoords(xyz, 'display', 'mesh')

        vidx = self.displayCtx.vertexIndex
        vert = self.overlay.vertices[vidx, :]

        if np.all(np.isclose(vert, xyz)):
            return vidx
        else:
            return None


    def transformCoords(self, coords, from_, to, vector=False):
        """Transforms the given ``coords`` from ``from_`` to ``to``.

        :arg coords: Coordinates to transform.
        :arg from_:  Space that the coordinates are in
        :arg to:     Space to transform the coordinates to
        :arg vector: Assume the coordinates are vectors.

        The following values are accepted for the ``from_`` and ``to``
        parameters:

          - ``'world'``:  World coordinate system
          - ``'display'`` Display coordinate system
          - ``'mesh'``    The coordinate system of this mesh.
        """

        if from_ not in ('world', 'display', 'mesh') or \
           to    not in ('world', 'display', 'mesh'):
            raise ValueError('Invalid space(s): {} -> {}'.format(from_, to))

        if self.refImage is None:
            return coords

        opts = self.displayCtx.getOpts(self.refImage)

        if from_ == 'mesh': from_ = self.coordSpace
        if to    == 'mesh': to    = self.coordSpace

        return opts.transformCoords(coords, from_, to, vector=vector)


    def __transformChanged(self, value, valid, ctx, name):
        """Called when the :attr:`.NiftiOpts.transform` property of the current
        :attr:`refImage` changes. Calls :meth:`__updateBounds`.
        """
        self.__updateBounds()


    def __coordSpaceChanged(self, *a):
        """Called when the :attr:`coordSpace` property changes.
        Calls :meth:`__updateBounds`.
        """
        self.__updateBounds()


    def __refImageChanged(self, *a):
        """Called when the :attr:`refImage` property changes.

        If a new reference image has been specified, removes listeners from
        the old one (if necessary), and adds listeners to the
        :attr:`.NiftiOpts.transform` property associated with the new image.
        Calls :meth:`__updateBounds`.
        """

        # TODO You are not tracking changes to the
        # refImage overlay type -  if this changes,
        # you will need to re-bind to the transform
        # property of the new DisplayOpts instance

        if self.__oldRefImage is not None and \
           self.__oldRefImage in self.overlayList:

            opts = self.displayCtx.getOpts(self.__oldRefImage)
            opts.removeListener('transform', self.name)

        self.__oldRefImage = self.refImage

        if self.refImage is not None:
            opts = self.displayCtx.getOpts(self.refImage)
            opts.addListener('transform',
                             self.name,
                             self.__transformChanged,
                             immediate=True)

        self.__updateBounds()


    def __updateBounds(self):
        """Called whenever any of the :attr:`refImage`, :attr:`coordSpace`,
        or :attr:`transform` properties change.

        Updates the :attr:`.DisplayOpts.bounds` property accordingly.
        """

        lo, hi = self.overlay.getBounds()
        xform  = self.getCoordSpaceTransform()

        lohi   = transform.transform([lo, hi], xform)
        lohi.sort(axis=0)
        lo, hi = lohi[0, :], lohi[1, :]

        oldBounds = self.bounds
        self.bounds = [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]

        if np.all(np.isclose(oldBounds, self.bounds)):
            self.propNotify('bounds')


    def __overlayListChanged(self, *a):
        """Called when the overlay list changes. Updates the :attr:`refImage`
        property so that it contains a list of overlays which can be
        associated with the mesh.
        """

        imgProp  = self.getProp('refImage')
        imgVal   = self.refImage
        overlays = self.displayCtx.getOrderedOverlays()

        # the overlay for this MeshOpts
        # instance has been removed
        if self.overlay not in overlays:
            self.overlayList.removeListener('overlays', self.name)
            return

        imgOptions = [None]

        for overlay in overlays:

            # The overlay must be a Nifti instance.
            if not isinstance(overlay, fslimage.Nifti):
                continue

            imgOptions.append(overlay)

            display = self.displayCtx.getDisplay(overlay)
            display.addListener('name',
                                self.name,
                                self.__overlayListChanged,
                                overwrite=True)

        # The previous refImage may have
        # been removed from the overlay list
        if imgVal in imgOptions: self.refImage = imgVal
        else:                    self.refImage = None

        imgProp.setChoices(imgOptions, instance=self)


    def __vertexDataChanged(self, *a):
        """Called when the :attr:`vertexData` property changes. Attempts to
        load the data if possible. The data may subsequently be retrieved
        via the :meth:`getVertexData` method.
        """

        vdata      = None
        vdataRange = None
        overlay    = self.overlay
        vdfile     = self.vertexData

        try:
            if vdfile is not None:

                if vdfile not in overlay.vertexDataSets():
                    log.debug('Loading vertex data: {}'.format(vdfile))
                    vdata = overlay.loadVertexData(vdfile)
                else:
                    vdata = overlay.getVertexData(vdfile)

                vdataRange = np.nanmin(vdata), np.nanmax(vdata)

                if len(vdata.shape) == 1:
                    vdata = vdata.reshape(-1, 1)

        except Exception as e:

            # TODO show a warning
            log.warning('Unable to load vertex data from {}: {}'.format(
                vdfile, e, exc_info=True))

            vdata      = None
            vdataRange = None

        self.__vertexData      = vdata
        self.__vertexDataRange = vdataRange

        if vdata is not None: npoints = vdata.shape[1]
        else:                 npoints = 1

        self.vertexDataIndex = 0
        self.setAttribute('vertexDataIndex', 'maxval', npoints - 1)

        self.updateDataRange()


    def __colourChanged(self, *a):
        """Called when :attr:`.colour` changes. Updates :attr:`.Display.alpha`
        from the alpha component.
        """

        alpha = self.colour[3] * 100

        log.debug('Propagating MeshOpts.colour[3] to '
                  'Display.alpha [{}]'.format(alpha))

        with props.skip(self.display, 'alpha', self.name):
            self.display.alpha = alpha


    def __alphaChanged(self, *a):
        """Called when :attr:`.Display.alpha` changes. Updates the alpha
        component of :attr:`.colour`.
        """

        alpha      = self.display.alpha / 100.0
        r, g, b, _ = self.colour

        log.debug('Propagating Display.alpha to MeshOpts.'
                  'colour[3] [{}]'.format(alpha))

        with props.skip(self, 'colour', self.name):
            self.colour = r, g, b, alpha
