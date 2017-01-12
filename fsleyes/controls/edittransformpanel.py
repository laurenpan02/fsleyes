#!/usr/bin/env python
#
# edittransformpanel.py - The EditTransformPanel class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`EditTransformPanel` class, a FSLeyes
control panel which allows the user to adjust the ``voxToWorldMat`` of an
:class:`.Image` overlay.
"""


import wx

import numpy as np

import pwidgets.floatslider as fslider
import fsl.data.image       as fslimage
import fsl.utils.async      as async
import fsl.utils.transform  as transform
import fsleyes.panel        as fslpanel
import fsleyes.strings      as strings


class EditTransformPanel(fslpanel.FSLeyesPanel):
    """The :class:`EditTransformPanel` class is a FSLeyes control panel which
    allows the user to adjust the ``voxToWorldMat`` of an :class:`.Image`
    overlay.

    
    Controls are provided allowing the user to construct a transformation
    matrix from scales, offsets, and rotations. While the user is adjusting
    the transformation, the :attr:`.NiftiOpts.displayXform` is used to
    update the overlay display in real time. When the user clicks the *Apply*
    button, the transformation is applied to the image's ``voxToWorldMat``
    attribute.

    
    .. note:: The :attr:`.DisplayContext.displaySpace` attribute must be
              set to ``'world'`` for the :attr:`.NiftiOpts.displayXform`
              updates to be seen immediately.
    """


    def __init__(self, parent, overlayList, displayCtx, frame, ortho):
        """Create an ``EditTransformPanel``.

        :arg parent:      The :mod:`wx` parent object.
        :arg overlayList: The :class:`.OverlayList` instance.
        :arg displayCtx:  The :class:`.DisplayContext` instance.
        :arg frame:       The :class:`.FSLeyesFrame` instance.
        :arg ortho:       The :class:`.OrthoPanel` instance. 
        """
        
        fslpanel.FSLeyesPanel.__init__(
            self, parent, overlayList, displayCtx, frame)

        self.__ortho   = ortho
        self.__overlay = None

        scArgs = {
            'value'    : 0,
            'minValue' : 0.001,
            'maxValue' : 10,
            'style'    : fslider.SSP_NO_LIMITS
        }        

        offArgs = {
            'value'    : 0,
            'minValue' : -250,
            'maxValue' :  250,
            'style'    : fslider.SSP_NO_LIMITS
        }
        
        rotArgs = {
            'value'    : 0,
            'minValue' : -180,
            'maxValue' :  180,
            'style'    : 0
        }

        self.__overlayName = wx.StaticText(self)

        self.__xscale  = fslider.SliderSpinPanel(self, label='X', **scArgs)
        self.__yscale  = fslider.SliderSpinPanel(self, label='Y', **scArgs)
        self.__zscale  = fslider.SliderSpinPanel(self, label='Z', **scArgs)
        
        self.__xoffset = fslider.SliderSpinPanel(self, label='X', **offArgs)
        self.__yoffset = fslider.SliderSpinPanel(self, label='Y', **offArgs)
        self.__zoffset = fslider.SliderSpinPanel(self, label='Z', **offArgs)

        self.__xrotate = fslider.SliderSpinPanel(self, label='X', **rotArgs)
        self.__yrotate = fslider.SliderSpinPanel(self, label='Y', **rotArgs)
        self.__zrotate = fslider.SliderSpinPanel(self, label='Z', **rotArgs)

        self.__scaleLabel  = wx.StaticText(self)
        self.__offsetLabel = wx.StaticText(self)
        self.__rotateLabel = wx.StaticText(self)

        self.__oldXformLabel = wx.StaticText(self)
        self.__oldXform      = wx.StaticText(self)
        self.__newXformLabel = wx.StaticText(self)
        self.__newXform      = wx.StaticText(self)

        self.__apply  = wx.Button(self)
        self.__reset  = wx.Button(self)
        self.__cancel = wx.Button(self)

        self.__overlayName  .SetLabel(strings.labels[self, 'noOverlay'])
        self.__scaleLabel   .SetLabel(strings.labels[self, 'scale'])
        self.__offsetLabel  .SetLabel(strings.labels[self, 'offset'])
        self.__rotateLabel  .SetLabel(strings.labels[self, 'rotate'])
        self.__apply        .SetLabel(strings.labels[self, 'apply'])
        self.__reset        .SetLabel(strings.labels[self, 'reset'])
        self.__cancel       .SetLabel(strings.labels[self, 'cancel'])
        self.__oldXformLabel.SetLabel(strings.labels[self, 'oldXform'])
        self.__newXformLabel.SetLabel(strings.labels[self, 'newXform'])

        # Populate the xform labels with a
        # dummy xform, so an appropriate
        # minimum size will get calculated
        # below 
        self.__formatXform(np.eye(4), self.__oldXform)
        self.__formatXform(np.eye(4), self.__newXform)

        self.__primarySizer   = wx.BoxSizer(wx.VERTICAL)
        self.__secondarySizer = wx.BoxSizer(wx.HORIZONTAL)
        self.__controlSizer   = wx.BoxSizer(wx.VERTICAL)
        self.__xformSizer     = wx.BoxSizer(wx.VERTICAL)
        self.__buttonSizer    = wx.BoxSizer(wx.HORIZONTAL)

        self.__primarySizer  .Add((1, 10),            flag=wx.EXPAND)
        self.__primarySizer  .Add(self.__overlayName, flag=wx.CENTRE)
        self.__primarySizer  .Add((1, 10),            flag=wx.EXPAND)
        self.__primarySizer  .Add(self.__secondarySizer)
        self.__primarySizer  .Add((1, 10),            flag=wx.EXPAND)
        self.__primarySizer  .Add(self.__buttonSizer, flag=wx.EXPAND)
        self.__primarySizer  .Add((1, 10), flag=wx.EXPAND)

        self.__secondarySizer.Add((10, 1),           flag=wx.EXPAND)
        self.__secondarySizer.Add(self.__controlSizer)
        self.__secondarySizer.Add((10, 1),           flag=wx.EXPAND)
        self.__secondarySizer.Add(self.__xformSizer, flag=wx.EXPAND)
        self.__secondarySizer.Add((10, 1),           flag=wx.EXPAND)

        self.__controlSizer.Add(self.__scaleLabel)
        self.__controlSizer.Add(self.__xscale)
        self.__controlSizer.Add(self.__yscale)
        self.__controlSizer.Add(self.__zscale)
        self.__controlSizer.Add(self.__offsetLabel)
        self.__controlSizer.Add(self.__xoffset)
        self.__controlSizer.Add(self.__yoffset)
        self.__controlSizer.Add(self.__zoffset)
        self.__controlSizer.Add(self.__rotateLabel)
        self.__controlSizer.Add(self.__xrotate)
        self.__controlSizer.Add(self.__yrotate)
        self.__controlSizer.Add(self.__zrotate)

        self.__xformSizer.Add((1, 1), flag=wx.EXPAND, proportion=1)
        self.__xformSizer.Add(self.__oldXformLabel)
        self.__xformSizer.Add(self.__oldXform)
        self.__xformSizer.Add((1, 1), flag=wx.EXPAND, proportion=1)
        self.__xformSizer.Add(self.__newXformLabel)
        self.__xformSizer.Add(self.__newXform)
        self.__xformSizer.Add((1, 1), flag=wx.EXPAND, proportion=1)

        self.__buttonSizer.Add((10, 1),       flag=wx.EXPAND, proportion=1)
        self.__buttonSizer.Add(self.__apply,  flag=wx.EXPAND)
        self.__buttonSizer.Add((10, 1),       flag=wx.EXPAND)
        self.__buttonSizer.Add(self.__reset,  flag=wx.EXPAND)
        self.__buttonSizer.Add((10, 1),       flag=wx.EXPAND) 
        self.__buttonSizer.Add(self.__cancel, flag=wx.EXPAND)
        self.__buttonSizer.Add((10, 1),       flag=wx.EXPAND, proportion=1) 

        self.SetSizer(self.__primarySizer)
        self.SetMinSize(self.__primarySizer.GetMinSize())

        self.__xscale .Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__yscale .Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__zscale .Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__xoffset.Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__yoffset.Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__zoffset.Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__xrotate.Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__yrotate.Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)
        self.__zrotate.Bind(fslider.EVT_SSP_VALUE, self.__xformChanged)

        self.__apply .Bind(wx.EVT_BUTTON, self.__onApply)
        self.__reset .Bind(wx.EVT_BUTTON, self.__onReset)
        self.__cancel.Bind(wx.EVT_BUTTON, self.__onCancel)
        
        displayCtx .addListener('selectedOverlay',
                                self._name,
                                self.__selectedOverlayChanged)
        overlayList.addListener('overlays',
                                self._name,
                                self.__selectedOverlayChanged)

        self.__selectedOverlayChanged()


    def destroy(self):
        """Must be called when this ``EditTransformPanel`` is no longer
        needed. Removes listeners and cleans up references.
        """

        self.__deregisterOverlay()
        self.__ortho = None

        displayCtx  = self.getDisplayContext()
        overlayList = self.getOverlayList()

        displayCtx .removeListener('selectedOverlay', self._name)
        overlayList.removeListener('overlays',        self._name)

        fslpanel.FSLeyesPanel.destroy(self)


    def __registerOverlay(self, overlay):
        """Called by :meth:`__selectedOverlayChanged`. Stores a reference
        to the given ``overlay``.
        """ 

        self.__overlay = overlay
        display = self.getDisplayContext().getDisplay(overlay)
        display.addListener('name', self._name, self.__overlayNameChanged)

        self.__overlayNameChanged()

        
    def __deregisterOverlay(self):
        """Called by :meth:`__selectedOverlayChanged`. Clears references
        to the most recently registered overlay.
        """

        if self.__overlay is None:
            return

        overlay = self.__overlay

        self.__overlay = None

        self.__overlayName.SetLabel(strings.labels[self, 'noOverlay'])

        display = self.getDisplayContext().getDisplay(overlay)
        display.removeListener('name', self._name)


    def __overlayNameChanged(self, *a):
        """Called when the :attr:`.Display.name` of the currently selected
        overlay changes. Updates the name label.
        """
        display = self.getDisplayContext().getDisplay(self.__overlay)
        label   = strings.labels[self, 'overlayName'].format(display.name)

        self.__overlayName.SetLabel(label)


    def __selectedOverlayChanged(self, *a):
        """Called when the :attr:`.DisplayContext.selectedOverlay` or
        :attr:`.OverlayList.overlays` properties change. If the newly
        selected overlay is an :class:`.Image`, it is registered, and
        the transform widgets reset.
        """
        overlay = self.getDisplayContext().getSelectedOverlay()

        if overlay is self.__overlay:
            return

        self.__deregisterOverlay()

        enabled = isinstance(overlay, fslimage.Image)

        self.Enable(enabled)

        if not enabled:
            return

        self.__registerOverlay(overlay)

        xform = overlay.voxToWorldMat

        self.__formatXform(xform, self.__oldXform)
        self.__formatXform(xform, self.__newXform)

        # TODO Set limits based on image size?
        self.__xscale .SetValue(1)
        self.__yscale .SetValue(1)
        self.__zscale .SetValue(1)
        self.__xoffset.SetValue(0)
        self.__yoffset.SetValue(0)
        self.__zoffset.SetValue(0)
        self.__xrotate.SetValue(0)
        self.__yrotate.SetValue(0)
        self.__zrotate.SetValue(0) 


    def __formatXform(self, xform, ctrl):
        """Format the given ``xform``  on the given ``wx.StaticText``
        ``ctrl``.
        """

        text = ''

        for rowi in range(xform.shape[0]):
            for coli in range(xform.shape[1]):

                text = text + '{: 9.2f} '.format(xform[rowi, coli])

            text = text + '\n'

        ctrl.SetLabel(text)


    def __getCurrentXform(self):
        """Returns the current transformation matrix defined by the scale,
        offset, and rotation widgets.
        """
        
        offsets   = [self.__xoffset.GetValue(),
                     self.__yoffset.GetValue(),
                     self.__zoffset.GetValue()]
        scales    = [self.__xscale .GetValue(),
                     self.__yscale .GetValue(),
                     self.__zscale .GetValue()]
        rotations = [self.__xrotate.GetValue(),
                     self.__yrotate.GetValue(),
                     self.__zrotate.GetValue()]

        rotations = [r * np.pi / 180 for r in rotations]

        shape     = self.__overlay.shape[:3]
        origin    = [sc * sh / 2.0 for sc, sh in zip(scales, shape)]

        return transform.compose(scales, offsets, rotations, origin)


    def __xformChanged(self, ev=None):
        """Called when any of the scale, offset, or rotate widgets are
        modified. Updates the :attr:`.NiftiOpts.displayXform` for the
        overlay currently being edited.
        """

        if self.__overlay is None:
            return

        overlay  = self.__overlay
        opts     = self.getDisplayContext().getOpts(overlay)

        newXform = self.__getCurrentXform()
        xform    = transform.concat(overlay.voxToWorldMat, newXform)

        self.__formatXform(xform, self.__newXform)
        opts.displayXform = newXform
    
    
    def __onApply(self, ev):
        """Called when the *Apply* button is pushed. Sets the
        ``voxToWorldMat`` attribute of the :class:`.Image` instance being
        transformed, and then calls the :meth:`__onCancel` to close this
        panel.
        """
        
        if self.__overlay is None:
            return
        
        newXform = self.__getCurrentXform()
        xform    = transform.concat(self.__overlay.voxToWorldMat, newXform)

        self.__overlay.voxToWorldMat = xform
        self.__onCancel()


    def __onReset(self, ev):
        """Called when the *Reset* button is pushed. Resets the
        transformation.
        """
        
        if self.__overlay is None:
            return
        
        opts = self.getDisplayContext().getOpts(self.__overlay)
        opts.displayXform = np.eye(4)
        
        self.__deregisterOverlay()
        self.__selectedOverlayChanged()


    def __onCancel(self, ev=None):
        """Called when the *Cancel* button is pushed, and also by the
        :meth:`__onApply` method. Resets the :attr:`.NiftiOpts.displayXform`
        attribute of the overlay being transformed, and then calls
        :meth:`.OrthoPanel.toggleEditTransformPanel` to close this panel.
        """
        
        if self.__overlay is not None:
            opts = self.getDisplayContext().getOpts(self.__overlay)
            opts.displayXform = np.eye(4)
            
        self.__deregisterOverlay()
        async.idle(self.__ortho.toggleEditTransformPanel)
