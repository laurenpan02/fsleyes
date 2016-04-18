#!/usr/bin/env python
#
# routines.py - A collection of disparate utility functions related to OpenGL.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module contains a collection of miscellaneous OpenGL routines. """


from __future__ import division

import logging

import itertools           as it

import OpenGL.GL           as gl
import numpy               as np

import fsl.utils.transform as transform


log = logging.getLogger(__name__)


def clear(bgColour):
    """Clears the current frame buffer, and does some standard setup
    operations.
    """

    # set the background colour
    gl.glClearColor(*bgColour)

    # clear the buffer
    gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

    # enable transparency
    gl.glEnable(gl.GL_BLEND) 
    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)


def show2D(xax, yax, width, height, lo, hi):
    """Configures the OpenGL viewport for 2D othorgraphic display.

    :arg xax:    Index (into ``lo`` and ``hi``) of the axis which
                 corresponds to the horizontal screen axis.
    :arg yax:    Index (into ``lo`` and ``hi``) of the axis which
                 corresponds to the vertical screen axis.
    :arg width:  Canvas width in pixels.
    :arg height: Canvas height in pixels.
    :arg lo:     Tuple containing the mininum ``(x, y, z)`` display
                 coordinates.
    :arg hi:     Tuple containing the maxinum ``(x, y, z)`` display
                 coordinates.
    """

    zax = 3 - xax - yax

    xmin, xmax = lo[xax], hi[xax]
    ymin, ymax = lo[yax], hi[yax]
    zmin, zmax = lo[zax], hi[zax]

    gl.glViewport(0, 0, width, height)
    gl.glMatrixMode(gl.GL_PROJECTION)
    gl.glLoadIdentity()

    zdist = max(abs(zmin), abs(zmax))

    log.debug('Configuring orthographic viewport: '
              'X: [{} - {}] Y: [{} - {}] Z: [{} - {}]'.format(
                  xmin, xmax, ymin, ymax, -zdist, zdist))

    gl.glOrtho(xmin, xmax, ymin, ymax, -zdist, zdist)
    gl.glMatrixMode(gl.GL_MODELVIEW)
    gl.glLoadIdentity()

    # Rotate world space so the displayed slice
    # is visible and correctly oriented
    # TODO There's got to be a more generic way
    # to perform this rotation. This will break
    # if I add functionality allowing the user
    # to specifty the x/y axes on initialisation.
    if zax == 0:
        gl.glRotatef(270, 1, 0, 0)
        gl.glRotatef(270, 0, 0, 1)
    elif zax == 1:
        gl.glRotatef(270, 1, 0, 0)


def calculateSamplePoints(shape, resolution, xform, xax, yax, origin='centre'):
    """Calculates a uniform grid of points, in the display coordinate system
    (as specified by the given :class:`.Display` object properties) along the
    x-y plane (as specified by the xax/yax indices), at which the given image
    should be sampled for display purposes.

    This function returns a tuple containing:

     - a numpy array of shape ``(N, 3)``, containing the coordinates of the
       centre of every sampling point in the display coordinate system.

     - the horizontal distance (along xax) between adjacent points

     - the vertical distance (along yax) between adjacent points

     - The number of samples along the horizontal axis (xax)

     - The number of samples along the vertical axis (yax)

    :arg shape:      The shape of the data to be sampled.

    :arg xform:      A transformation matrix which converts from data 
                     coordinates to the display coordinate system.

    :arg resolution: The desired resolution in display coordinates, along
                     each display axis.

    :arg xax:        The horizontal display coordinate system axis (0, 1, or
                     2).

    :arg yax:        The vertical display coordinate system axis (0, 1, or 2).

    :arg origin:     ``centre`` or ``corner``. See the
                     :func:`.transform.axisBounds` function.
    """

    xres = resolution[xax]
    yres = resolution[yax]

    # These values give the min/max x/y
    # values of a bounding box which
    # encapsulates the entire image,
    # in the display coordinate system
    xmin, xmax = transform.axisBounds(shape, xform, xax, origin, boundary=None)
    ymin, ymax = transform.axisBounds(shape, xform, yax, origin, boundary=None)

    # Number of samples along each display
    # axis, given the requested resolution
    xNumSamples = np.floor((xmax - xmin) / xres)
    yNumSamples = np.floor((ymax - ymin) / yres)

    # adjust the x/y resolution so
    # the samples fit exactly into
    # the data bounding box
    xres = (xmax - xmin) / xNumSamples
    yres = (ymax - ymin) / yNumSamples

    # Calculate the locations of every 
    # sample point in display space
    worldX = np.linspace(xmin + 0.5 * xres,
                         xmax - 0.5 * xres,
                         xNumSamples)
    worldY = np.linspace(ymin + 0.5 * yres,
                         ymax - 0.5 * yres,
                         yNumSamples)

    worldX, worldY = np.meshgrid(worldX, worldY)
    
    coords = np.zeros((worldX.size, 3), dtype=np.float32)
    coords[:, xax] = worldX.flatten()
    coords[:, yax] = worldY.flatten()

    return coords, xres, yres, xNumSamples, yNumSamples


def samplePointsToTriangleStrip(coords,
                                xpixdim,
                                ypixdim,
                                xlen,
                                ylen,
                                xax,
                                yax):
    """Given a regular 2D grid of points at which an image is to be sampled
    (for example, that generated by the :func:`calculateSamplePoints` function
    above), converts those points into an OpenGL vertex triangle strip.

    A grid of ``M*N`` points is represented by ``M*2*(N + 1)`` vertices. For
    example, this image represents a 4*3 grid, with periods representing vertex
    locations::
    
        .___.___.___.___.
        |   |   |   |   |
        |   |   |   |   |
        .---.---.---.---.
        .___.___.__ .___.
        |   |   |   |   |
        |   |   |   |   |
        .---.---.---.---.
        .___.___.___.___.
        |   |   |   |   |
        |   |   |   |   |
        .___.___.___.___.

    
    Vertex locations which are vertically adjacent represent the same point in
    space. Such vertex pairs are unable to be combined because, in OpenGL,
    they must be represented by distinct vertices (we can't apply multiple
    colours/texture coordinates to a single vertex location) So we have to
    repeat these vertices in order to achieve accurate colouring of each
    voxel.

    We draw each horizontal row of samples one by one, using two triangles to
    draw each voxel. In order to eliminate the need to specify six vertices
    for every voxel, and hence to reduce the amount of memory used, we are
    using a triangle strip to draw each row of voxels. This image depicts a
    triangle strip used to draw a row of three samples (periods represent
    vertex locations)::


        1  3  5  7
        .  .  .  .
        |\ |\ |\ |
        | \| \| \|
        .  .  .  .
        0  2  4  6
      
    In order to use a single OpenGL call to draw multiple non-contiguous voxel
    rows, between every column we add a couple of 'dummy' vertices, which will
    then be interpreted by OpenGL as 'degenerate triangles', and will not be
    drawn. So in reality, a 4*3 slice would be drawn as follows (with vertices
    labelled from ``[a-z0-9]``::

         v  x  z  1  33
         |\ |\ |\ |\ |
         | \| \| \| \|
        uu  w  y  0  2
         l  n  p  r  tt
         |\ |\ |\ |\ |
         | \| \| \| \|
        kk  m  o  q  s  
         b  d  f  h  jj
         |\ |\ |\ |\ |
         | \| \| \| \|
         a  c  e  g  i
    
    These repeated/degenerate vertices are dealt with by using a vertex index
    array.  See these links for good overviews of triangle strips and
    degenerate triangles in OpenGL:
    
     - http://www.learnopengles.com/tag/degenerate-triangles/
     - http://en.wikipedia.org/wiki/Triangle_strip

    A tuple is returned containing:

      - A 2D ``numpy.float32`` array of shape ``(2 * (xlen + 1) * ylen), 3)``,
        containing the coordinates of all triangle strip vertices which
        represent the entire grid of sample points.
    
      - A 2D ``numpy.float32`` array of shape ``(2 * (xlen + 1) * ylen), 3)``,
        containing the centre of every grid, to be used for texture
        coordinates/colour lookup.
    
      - A 1D ``numpy.uint32`` array of size ``ylen * (2 * (xlen + 1) + 2) - 2``
        containing indices into the first array, defining the order in which
        the vertices need to be rendered. There are more indices than vertex
        coordinates due to the inclusion of repeated/degenerate vertices.

    :arg coords:  N*3 array of points, the sampling locations.
    
    :arg xpixdim: Length of one sample along the horizontal axis.
    
    :arg ypixdim: Length of one sample along the vertical axis.
    
    :arg xlen:    Number of samples along the horizontal axis.
    
    :arg ylen:    Number of samples along the vertical axis.
    
    :arg xax:     Display coordinate system axis which corresponds to the
                  horizontal screen axis.
    
    :arg yax:     Display coordinate system axis which corresponds to the
                  vertical screen axis.
    """

    coords = coords.reshape(ylen, xlen, 3)

    xlen = int(xlen)
    ylen = int(ylen)

    # Duplicate every row - each voxel
    # is defined by two vertices 
    coords = coords.repeat(2, 0)

    texCoords   = np.array(coords, dtype=np.float32)
    worldCoords = np.array(coords, dtype=np.float32)

    # Add an extra column at the end
    # of the world coordinates
    worldCoords = np.append(worldCoords, worldCoords[:, -1:, :], 1)
    worldCoords[:, -1, xax] += xpixdim

    # Add an extra column at the start
    # of the texture coordinates
    texCoords = np.append(texCoords[:, :1, :], texCoords, 1)

    # Move the x/y world coordinates to the
    # sampling point corners (the texture
    # coordinates remain in the voxel centres)
    worldCoords[   :, :, xax] -= 0.5 * xpixdim
    worldCoords[ ::2, :, yax] -= 0.5 * ypixdim
    worldCoords[1::2, :, yax] += 0.5 * ypixdim 

    vertsPerRow  = 2 * (xlen + 1) 
    dVertsPerRow = 2 * (xlen + 1) + 2
    nindices     = ylen * dVertsPerRow - 2

    indices = np.zeros(nindices, dtype=np.uint32)

    for yi, xi in it.product(range(ylen), range(xlen + 1)):
        
        ii = yi * dVertsPerRow + 2 * xi
        vi = yi *  vertsPerRow + xi
        
        indices[ii]     = vi
        indices[ii + 1] = vi + xlen + 1

        # add degenerate vertices at the end
        # every row (but not needed for last
        # row)
        if xi == xlen and yi < ylen - 1:
            indices[ii + 2] = vi + xlen + 1
            indices[ii + 3] = (yi + 1) * vertsPerRow

    worldCoords = worldCoords.reshape((xlen + 1) * (2 * ylen), 3)
    texCoords   = texCoords  .reshape((xlen + 1) * (2 * ylen), 3)

    return worldCoords, texCoords, indices


def voxelGrid(points, xax, yax, xpixdim, ypixdim):
    """Given a ``N*3`` array of ``points`` (assumed to be voxel
    coordinates), creates an array of vertices which can be used
    to render each point as an unfilled rectangle.

    :arg points:  An ``N*3`` array of voxel xyz coordinates

    :arg xax:     XYZ axis index that maps to the horizontal scren axis
    
    :arg yax:     XYZ axis index that maps to the vertical scren axis
    
    :arg xpixdim: Length of a voxel along the x axis.
    
    :arg ypixdim: Length of a voxel along the y axis.
    """

    if len(points.shape) == 1:
        points = points.reshape(1, 3)

    npoints  = points.shape[0]
    vertices = np.repeat(np.array(points, dtype=np.float32), 4, axis=0)

    xpixdim = xpixdim / 2.0
    ypixdim = ypixdim / 2.0

    # bottom left corner
    vertices[ ::4, xax] -= xpixdim 
    vertices[ ::4, yax] -= ypixdim

    # bottom right
    vertices[1::4, xax] += xpixdim
    vertices[1::4, yax] -= ypixdim
    
    # top left
    vertices[2::4, xax] -= xpixdim
    vertices[2::4, yax] += ypixdim

    # top right
    vertices[3::4, xax] += xpixdim
    vertices[3::4, yax] += ypixdim

    # each square is rendered as four lines
    indices = np.array([0, 1, 0, 2, 1, 3, 2, 3], dtype=np.uint32)
    indices = np.tile(indices, npoints)
    
    indices = (indices.T +
               np.repeat(np.arange(0, npoints * 4, 4, dtype=np.uint32), 8)).T
    
    return vertices, indices


def slice2D(dataShape,
            xax,
            yax,
            zpos,
            voxToDisplayMat,
            displayToVoxMat,
            geometry='triangles',
            origin='centre'):
    """Generates and returns vertices which denote a slice through an
    array of the given ``dataShape``, parallel to the plane defined by the
    given ``xax`` and ``yax`` and at the given z position, in the space
    defined by the given ``voxToDisplayMat``.

    If ``geometry`` is ``triangles`` (the default), six vertices are returned,
    arranged as follows::

         4---5
        1 \  |
        |\ \ |
        | \ \| 
        |  \ 3
        0---2

    Otherwise, if geometry is ``square``, four vertices are returned, arranged
    as follows::

         
        3---2
        |   |
        |   |
        |   |
        0---1

    If ``origin`` is set to ``centre`` (the default), it is assumed that
    a voxel at location ``(x, y, z)`` is located in the space::
    
        (x - 0.5 : x + 0.5, y - 0.5 : y + 0.5, z - 0.5 : z + 0.5)

    
    Otherwise, if ``origin`` is set to ``corner``, a voxel at location ``(x,
    y, z)`` is assumed to be located in the space::

        (x : x + 1, y : y + 1, z : z + 1)

    
    :arg dataShape:       Number of elements along each dimension in the
                          image data.
    
    :arg xax:             Index of display axis which corresponds to the
                          horizontal screen axis.

    :arg yax:             Index of display axis which corresponds to the
                          vertical screen axis.

    :arg zpos:            Position of the slice along the screen z axis.
    
    :arg voxToDisplayMat: Affine transformation matrix which transforms from
                          voxel/array indices into the display coordinate
                          system.

    :arg displayToVoxMat: Inverse of the ``voxToDisplayMat``.

    :arg geometry:        ``square`` or ``triangle``.

    :arg origin:          ``centre`` or ``corner``. See the
                          :func:`.transform.axisBounds` function.
    
    Returns a tuple containing:
    
      - A ``N*3`` ``numpy.float32`` array containing the vertex locations
        of a slice through the data, where ``N=6`` if ``geometry=triangles``,
        or ``N=4`` if ``geometry=square``,

      - A ``N*3`` ``numpy.float32`` array containing the voxel coordinates
        that correspond to the vertex locations.

      - A ``N*3`` ``numpy.float32`` array containing the texture coordinates
        that correspond to the voxel coordinates.
    """

    zax        = 3 - xax - yax
    xmin, xmax = transform.axisBounds(
        dataShape, voxToDisplayMat, xax, origin, boundary=None)
    ymin, ymax = transform.axisBounds(
        dataShape, voxToDisplayMat, yax, origin, boundary=None)

    if geometry == 'triangles':

        vertices = np.zeros((6, 3), dtype=np.float32)

        vertices[ 0, [xax, yax]] = [xmin, ymin]
        vertices[ 1, [xax, yax]] = [xmin, ymax]
        vertices[ 2, [xax, yax]] = [xmax, ymin]
        vertices[ 3, [xax, yax]] = [xmax, ymin]
        vertices[ 4, [xax, yax]] = [xmin, ymax]
        vertices[ 5, [xax, yax]] = [xmax, ymax]
        
    elif geometry == 'square':
        vertices = np.zeros((4, 3), dtype=np.float32)

        vertices[ 0, [xax, yax]] = [xmin, ymin]
        vertices[ 1, [xax, yax]] = [xmax, ymin]
        vertices[ 2, [xax, yax]] = [xmax, ymax]
        vertices[ 3, [xax, yax]] = [xmin, ymax]
    else:
        raise ValueError('Unrecognised geometry type: {}'.format(geometry))

    vertices[:, zax] = zpos

    voxCoords = transform.transform(vertices, displayToVoxMat)

    # offset by 0.5, because voxel coordinates are by
    # default centered at 0 (i.e. the space of a voxel
    # lies in the range [-0.5, 0.5]), but we want voxel
    # coordinates to map to the effective range [0, 1]
    if origin == 'centre':
        voxCoords = voxCoords + 0.5
        texCoords = voxCoords / dataShape

    # If the origin is the voxel corner, we still need
    # to offset the texture coordinates, as the voxel
    # coordinate range [-0.5, shape-0.5] must be scaled
    # to the texture coordinate range [0.0, 1.0].
    elif origin == 'corner':
        texCoords = (voxCoords + 0.5) / dataShape
        
    else:
        raise ValueError('Unrecognised origin: {}'.format(origin))

    return vertices, voxCoords, texCoords


def subsample(data, resolution, pixdim=None, volume=None):
    """Samples the given 3D data according to the given resolution.

    Returns a tuple containing:

      - A 3D numpy array containing the sub-sampled data.

      - A tuple containing the ``(x, y, z)`` starting indices of the
        sampled data.

      - A tuple containing the ``(x, y, z)`` steps of the sampled data.

    :arg data:       The data to be sampled.

    :arg resolution: Sampling resolution, proportional to the values in
                     ``pixdim``.

    :arg pixdim:     Length of each dimension in the input data (defaults to
                     ``(1.0, 1.0, 1.0)``).

    :arg volume:     If the image is a 4D volume, the volume index of the 3D
                     image to be sampled.
    """

    if pixdim is None:
        pixdim = (1.0, 1.0, 1.0)

    if volume is None:
        volume = slice(None, None, None)

    xstep = int(np.round(resolution / pixdim[0]))
    ystep = int(np.round(resolution / pixdim[1]))
    zstep = int(np.round(resolution / pixdim[2]))

    if xstep < 1: xstep = 1
    if ystep < 1: ystep = 1
    if zstep < 1: zstep = 1

    xstart = int(np.floor(xstep / 2))
    ystart = int(np.floor(ystep / 2))
    zstart = int(np.floor(zstep / 2))

    if xstart >= data.shape[0]: xstart = data.shape[0] - 1
    if ystart >= data.shape[1]: ystart = data.shape[1] - 1
    if zstart >= data.shape[2]: zstart = data.shape[2] - 1
        
    if len(data.shape) > 3: sample = data[xstart::xstep,
                                          ystart::ystep,
                                          zstart::zstep,
                                          volume]
    else:                   sample = data[xstart::xstep,
                                          ystart::ystep,
                                          zstart::zstep]

    return sample, (xstart, ystart, zstart), (xstep, ystep, zstep)


def broadcast(vertices, indices, zposes, xforms, zax):
    """Given a set of vertices and indices (assumed to be 2D representations
    of some geometry in a 3D space, with the depth axis specified by ``zax``),
    replicates them across all of the specified Z positions, applying the
    corresponding transformation to each set of vertices.

    :arg vertices: Vertex array (a ``N*3`` numpy array).
    
    :arg indices:  Index array.
    
    :arg zposes:   Positions along the depth axis at which the vertices
                   are to be replicated.
    
    :arg xforms:   Sequence of transformation matrices, one for each
                   Z position.
    
    :arg zax:      Index of the 'depth' axis

    Returns three values:
    
      - A numpy array containing all of the generated vertices
    
      - A numpy array containing the original vertices for each of the
        generated vertices, which may be used as texture coordinates

      - A new numpy array containing all of the generated indices.
    """

    vertices = np.array(vertices)
    indices  = np.array(indices)
    
    nverts   = vertices.shape[0]
    nidxs    = indices.shape[ 0]

    allTexCoords  = np.zeros((nverts * len(zposes), 3), dtype=np.float32)
    allVertCoords = np.zeros((nverts * len(zposes), 3), dtype=np.float32)
    allIndices    = np.zeros( nidxs  * len(zposes),     dtype=np.uint32)
    
    for i, (zpos, xform) in enumerate(zip(zposes, xforms)):

        vertices[:, zax] = zpos

        vStart = i * nverts
        vEnd   = vStart + nverts

        iStart = i * nidxs
        iEnd   = iStart + nidxs

        allIndices[   iStart:iEnd]    = indices + i * nverts
        allTexCoords[ vStart:vEnd, :] = vertices
        allVertCoords[vStart:vEnd, :] = transform.transform(vertices, xform)
        
    return allVertCoords, allTexCoords, allIndices


def planeEquation(xyz1, xyz2, xyz3):
    """Calculates the equation of a plane which contains each
    of the given points.

    Returns a tuple containing four values, the coefficients of the
    equation:

    :math:`a\\times x + b\\times y + c \\times z = d`

    for any point ``(x, y, z)`` that lies on the plane.

    See http://paulbourke.net/geometry/pointlineplane/ for details on plane
    equations.
    """
    x1, y1, z1 = xyz1
    x2, y2, z2 = xyz2
    x3, y3, z3 = xyz3

    eq = np.zeros(4, dtype=np.float64)

    eq[0] = (y1 * (z2 - z3)) + (y2 * (z3 - z1)) + (y3 * (z1 - z2))
    eq[1] = (z1 * (x2 - x3)) + (z2 * (x3 - x1)) + (z3 * (x1 - x2))
    eq[2] = (x1 * (y2 - y3)) + (x2 * (y3 - y1)) + (x3 * (y1 - y2))
    eq[3] = -((x1 * ((y2 * z3) - (y3 * z2))) +
              (x2 * ((y3 * z1) - (y1 * z3))) +
              (x3 * ((y1 * z2) - (y2 * z1))))

    return eq


def unitSphere(res):
    """Generates a unit sphere, as described in the *Sphere Generation*
    article, on Paul Bourke's excellent website:

        http://paulbourke.net/geometry/circlesphere/

    :arg res: Resolution - the number of angles to sample.

    :returns: A tuple comprising:
    
              - a ``numpy.float32`` array of size ``(res**2, 3)``
                containing a set of ``(x, y, z)`` vertices which define
                the ellipsoid surface.
     
              - A ``numpy.uint32`` array of size ``(4 * (res - 1)**2)``
                containing a list of indices into the vertex array,
                defining a vertex ordering that can be used to draw
                the ellipsoid using the OpenGL ``GL_QUAD`` primitive type.


    .. todo:: Generate indices to use with ``GL_TRIANGLES`` instead of
              ``GL_QUADS``.
    """

    # All angles to be sampled
    u = np.linspace(-np.pi / 2, np.pi / 2, res, dtype=np.float32)
    v = np.linspace(-np.pi,     np.pi,     res, dtype=np.float32)

    cosu = np.cos(u)
    cosv = np.cos(v)
    sinu = np.sin(u)
    sinv = np.sin(v) 

    cucv = np.outer(cosu, cosv)
    cusv = np.outer(cosu, sinv)

    vertices = np.zeros((res ** 2, 3), dtype=np.float32)

    # All x coordinates are of the form cos(u) * cos(v),
    # y coordinates are of the form cos(u) * sin(v),
    # and z coordinates of the form sin(u).
    vertices[:, 0] = cucv.flatten()
    vertices[:, 1] = cusv.flatten()
    vertices[:, 2] = sinu.repeat(res)

    # Generate a list of indices which join the
    # vertices so they can be used to draw the
    # sphere as GL_QUADs.
    # 
    # The vertex locations for each quad follow
    # this pattern:
    # 
    #  1. (u,         v)
    #  2. (u + ustep, v)
    #  3. (u + ustep, v + vstep)
    #  4. (u,         v + vstep)
    nquads   = (res - 1) ** 2
    quadIdxs = np.array([0, res, res + 1, 1], dtype=np.uint32)

    indices  = np.tile(quadIdxs, nquads)
    indices += np.arange(nquads,  dtype=np.uint32).repeat(4)
    indices += np.arange(res - 1, dtype=np.uint32).repeat(4 * (res - 1))
    
    return vertices, indices


def fullUnitSphere(res):
    """Generates a unit sphere in the same way as :func:`unitSphere`, but
    returns all vertices, instead of the unique vertices and an index array.

    :arg res: Resolution - the number of angles to sample.

    :returns: A ``numpy.float32`` array of size ``(4 * (res - 1)**2, 3)``
              containing the ``(x, y, z)`` vertices which can be used to draw
              a unit sphere (using the ``GL_QUADS`` primitive type).
    """

    u = np.linspace(-np.pi / 2, np.pi / 2, res, dtype=np.float32)
    v = np.linspace(-np.pi,     np.pi,     res, dtype=np.float32)

    cosu = np.cos(u)
    cosv = np.cos(v)
    sinu = np.sin(u)
    sinv = np.sin(v) 

    vertices = np.zeros(((res - 1) * (res - 1) * 4, 3), dtype=np.float32)

    cucv   = np.outer(cosu[:-1], cosv[:-1]).flatten()
    cusv   = np.outer(cosu[:-1], sinv[:-1]).flatten()
    cu1cv  = np.outer(cosu[1:],  cosv[:-1]).flatten()
    cu1sv  = np.outer(cosu[1:],  sinv[:-1]).flatten()
    cu1cv1 = np.outer(cosu[1:],  cosv[1:]) .flatten()
    cu1sv1 = np.outer(cosu[1:],  sinv[1:]) .flatten()
    cucv1  = np.outer(cosu[:-1], cosv[1:]) .flatten()
    cusv1  = np.outer(cosu[:-1], sinv[1:]) .flatten()
    
    su     = np.repeat(sinu[:-1], res - 1)
    s1u    = np.repeat(sinu[1:],  res - 1)

    vertices.T[:,  ::4] = [cucv,   cusv,   su]
    vertices.T[:, 1::4] = [cu1cv,  cu1sv,  s1u]
    vertices.T[:, 2::4] = [cu1cv1, cu1sv1, s1u]
    vertices.T[:, 3::4] = [cucv1,  cusv1,  su]

    return vertices