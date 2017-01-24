#!/usr/bin/env python
#
# melodicclassificationpanel.py - The MelodicClassificationPanel class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`MelodicClassificationPanel` class, a
*FSLeyes control* panel which allows the user to classify the components
of a :class:`.MelodicImage`.
"""


import os
import os.path as op
import logging

import wx

import props

import pwidgets.notebook                as notebook

import fsl.utils.settings               as fslsettings
import fsl.data.melodiclabels           as fslmellabels
import fsl.data.melodicimage            as fslmelimage
import fsleyes.displaycontext           as displaycontext
import fsleyes.colourmaps               as fslcm
import fsleyes.panel                    as fslpanel
import fsleyes.autodisplay              as autodisplay
import fsleyes.strings                  as strings
from . import componentgrid             as componentgrid
from . import labelgrid                 as labelgrid


log = logging.getLogger(__name__)


class MelodicClassificationPanel(fslpanel.FSLeyesPanel):
    """The ``MelodicClassificationPanel`` allows the user to view and modify
    classification labels associated with the components of a
    :class:`.MelodicImage`.

    It contains two lists:
    
      - The :class:`.ComponentGrid` contains list of components, and the
        labels associated with each.

      - The :class:`.LabelGrid` contains list of labels, and the
        components associated with each.

    And a handful of buttons which allow the user to:

     - Load a label file

     - Save the current labels to a file

     - Clear/reset the current labels
    """

    
    def __init__(self, parent, overlayList, displayCtx, frame, canvasPanel):
        """Create a ``MelodicClassificationPanel``.

        :arg parent:      The :mod:`wx` parent object.
        
        :arg overlayList: The :class:`.OverlayList`.
        
        :arg displayCtx:  The :class:`.DisplayContext` instance.

        :arg canvasPanel: The :class:`.CanvasPanel` that owns this
                          classification panel.
        """ 
        fslpanel.FSLeyesPanel.__init__(
            self, parent, overlayList, displayCtx, frame)

        self.__disabledText = wx.StaticText(
            self,
            style=(wx.ALIGN_CENTRE_HORIZONTAL |
                   wx.ALIGN_CENTRE_VERTICAL))

        self.__overlay       = None
        self.__canvasPanel   = canvasPanel
        self.__lut           = fslcm.getLookupTable('melodic-classes')

        # If this classification panel has been
        # added to a LightBoxPanel, we add a text
        # annotation to said lightbox panel, to
        # display the labels associated with the
        # currently displayed component.
        self.__textAnnotation = None
        from fsleyes.views.lightboxpanel import LightBoxPanel

        if isinstance(canvasPanel, LightBoxPanel):
            annot = canvasPanel.getCanvas().getAnnotations()
            self.__textAnnotation = annot.text(
                '',
                0.5, 1.0,
                fontSize=30,
                halign='centre',
                valign='top',
                width=2,
                hold=True)
        
        self.__notebook      = notebook.Notebook(self)
        self.__componentGrid = componentgrid.ComponentGrid(
            self.__notebook,
            overlayList,
            displayCtx,
            frame,
            self.__lut)

        self.__labelGrid     = labelgrid.LabelGrid(
            self.__notebook,
            overlayList,
            displayCtx,
            frame,
            self.__lut)

        self.__loadButton  = wx.Button(self)
        self.__saveButton  = wx.Button(self)
        self.__clearButton = wx.Button(self)

        self.__notebook.AddPage(self.__componentGrid,
                                strings.labels[self, 'componentTab'])
        self.__notebook.AddPage(self.__labelGrid,
                                strings.labels[self, 'labelTab'])

        self.__loadButton .SetLabel(strings.labels[self, 'loadButton'])
        self.__saveButton .SetLabel(strings.labels[self, 'saveButton'])
        self.__clearButton.SetLabel(strings.labels[self, 'clearButton'])

        # Things which you don't want shown when
        # a melodic image is not selected should
        # be added to __mainSizer. Things which
        # you always want displayed should be
        # added to __sizer (but need to be laid
        # out w.r.t. __disabledText/__mainSizer)
 
        self.__mainSizer = wx.BoxSizer(wx.VERTICAL)
        self.__btnSizer  = wx.BoxSizer(wx.HORIZONTAL)
        self.__sizer     = wx.BoxSizer(wx.VERTICAL)

        self.__btnSizer .Add(self.__loadButton,   flag=wx.EXPAND, proportion=1)
        self.__btnSizer .Add(self.__saveButton,   flag=wx.EXPAND, proportion=1)
        self.__btnSizer .Add(self.__clearButton,  flag=wx.EXPAND, proportion=1)
        
        self.__mainSizer.Add(self.__notebook,     flag=wx.EXPAND, proportion=1)

        self.__sizer    .Add(self.__disabledText, flag=wx.EXPAND, proportion=1)
        self.__sizer    .Add(self.__mainSizer,    flag=wx.EXPAND, proportion=1)
        self.__sizer    .Add(self.__btnSizer,     flag=wx.EXPAND)

        self.SetSizer(self.__sizer)

        self.__loadButton .Bind(wx.EVT_BUTTON, self.__onLoadButton)
        self.__saveButton .Bind(wx.EVT_BUTTON, self.__onSaveButton)
        self.__clearButton.Bind(wx.EVT_BUTTON, self.__onClearButton)

        overlayList.addListener('overlays',
                                self._name,
                                self.__selectedOverlayChanged)
        displayCtx .addListener('selectedOverlay',
                                self._name,
                                self.__selectedOverlayChanged)

        self.__selectedOverlayChanged()

        self.SetMinSize((400, 100))


    def destroy(self):
        """Must be called when this ``MelodicClassificaiionPanel`` is no longer
        used. Removes listeners, and destroys widgets.
        """


        if self.__textAnnotation is not None:
            annot = self.__canvasPanel.getCanvas().getAnnotations()
            annot.dequeue(self.__textAnnotation, hold=True)
        
        self._displayCtx .removeListener('selectedOverlay', self._name)
        self._overlayList.removeListener('overlays',        self._name)
        self.__componentGrid.destroy()
        self.__labelGrid    .destroy()
        
        self.__deregisterOverlay()
        self.__canvasPanel    = None
        self.__textAnnotation = None
        self.__overlay        = None
        self.__lut            = None
 
        fslpanel.FSLeyesPanel.destroy(self)


    def __enable(self, enable=True, message=''):
        """Called internally. Enables/disables this
        ``MelodicClassificationPanel``.
        """

        self.__disabledText.SetLabel(message)
        
        self.__sizer.Show(self.__disabledText, not enable)
        self.__sizer.Show(self.__mainSizer,    enable)

        self.__saveButton .Enable(enable)
        self.__clearButton.Enable(enable)

        if self.__textAnnotation is not None:
            self.__textAnnotation.enabled = enable

        self.Layout()


    def __deregisterOverlay(self):
        """Called by :meth:`__selectedOverlayChanged`. Deregisters from
        the currently selected overlay.
        """

        from fsleyes.views.lightboxpanel import LightBoxPanel

        overlay        = self.__overlay
        self.__overlay = None
        
        if overlay is None or \
           not isinstance(self.__canvasPanel, LightBoxPanel):
            return

        melclass = overlay.getICClassification()
        melclass.deregister(self._name)

        try:
            opts = self.getDisplayContext().getOpts(overlay)
            opts.removeListener('volume', self._name)
            
        except displaycontext.InvalidOverlayError:
            pass

        
    def __registerOverlay(self, overlay):
        """Called by :meth:`__selectedOverlayChanged`. Registers with
        the given overlay.
        """ 

        from fsleyes.views.lightboxpanel import LightBoxPanel

        self.__overlay = overlay

        if not isinstance(self.__canvasPanel, LightBoxPanel):
            return

        opts     = self.getDisplayContext().getOpts(overlay)
        melclass = overlay.getICClassification()

        opts.addListener('volume', self._name, self.__volumeChanged)
        melclass.register(self._name, self.__labelsChanged, topic='added')
        melclass.register(self._name, self.__labelsChanged, topic='removed')
        
        self.__updateTextAnnotation()

    
    def __selectedOverlayChanged(self, *a):
        """Called when the :attr:`.DisplayContext.selectedOverlay` or
        :attr:`.OverlayList.overlays` changes.

        The overlay is passed to the :meth:`.ComponentGrid.setOverlay`
        and :meth:`.LabelGrid.setOverlay` methods.

        If the newly selected overlay is not a :class:`.MelodicImage`,
        this panel is disabled (via :meth:`__enable`).
        """

        overlay = self._displayCtx.getSelectedOverlay()

        if self.__overlay is overlay:
            return

        self.__componentGrid.setOverlay(overlay)
        self.__labelGrid    .setOverlay(overlay)

        self.__deregisterOverlay()

        if (overlay is None) or \
           not isinstance(overlay, fslmelimage.MelodicImage):
            self.__enable(False, strings.messages[self, 'disabled'])

        else:
            self.__registerOverlay(overlay)
            self.__enable(True)


    def __volumeChanged(self, *a):
        """Called when the :attr:`.NiftiOpts.volume` property of the
        currently selected overlay changes. Calls
        :meth:`__updateTextAnnotation`
        
        .. note:: This method is only called if the view panel that
                  owns this ``MelodicClassificationPanel`` is a
                  :class:`.LightBoxPanel`.
        """
        self.__updateTextAnnotation()

        
    def __labelsChanged(self, *a):
        """Called when the :class:`.MelodicClassification` object associated
        with the currently selected overlay changes. Calls
        :meth:`__updateTextAnnotation`
        
        .. note:: This method is only called if the view panel that
                  owns this ``MelodicClassificationPanel`` is a
                  :class:`.LightBoxPanel`.
        """
        self.__updateTextAnnotation()

        # Label change will not necessarily trigger a
        # canvas refresh, so we manually trigger one
        self.__canvasPanel.Refresh()


    def __updateTextAnnotation(self):
        """Updates a text annotation on the :class:`.LightBoxPanel` canvas to
        display the labels associated with the volume (i.e. the current
        component).
        """
        
        opts     = self.getDisplayContext().getOpts(self.__overlay)
        melclass = self.__overlay.getICClassification()

        labels   = melclass.getLabels(opts.volume)
        labels   = [melclass.getDisplayLabel(l) for l in labels]

        colour   = self.__lut.getByName(labels[0]).colour

        self.__textAnnotation.text   = ', '.join(labels)
        self.__textAnnotation.colour = colour

        
    def __onLoadButton(self, ev):
        """Called when the *Load labels* button is pushed.  Prompts the user
        to select a label file to load, then does the following:

        1. If the selected label file refers to the currently selected
           melodic_IC overlay, the labels are applied to the overlay.

        2. If the selected label file refers to a different melodic_IC
           overlay, the user is asked whether they want to load the
           different melodic_IC file (the default), or whether they
           want the labels applied to the existing overlay.

        3. If the selected label file does not refer to any overlay
           (it only contains the bad component list), the user is asked
           whether they want the labels applied to the current melodic_IC
           overlay.

        If the number of labels in the file is less than the number of
        melodic_IC components, the remaining components are labelled
        as unknown. If the number of labels in the file is greater than
        the number of melodic_IC components, an error is shown, and
        nothing is done.
        """

        # The aim of the code beneath the
        # applyLabels function is to load
        # a set of component labels, and
        # to figure out which overlay
        # they should be added to.

        # When it has done this, it calls
        # applyLabels, which applies the
        # loaded labels to the overlay.
        def applyLabels(labelFile, overlay, allLabels, newOverlay):
            # labelFile:  Path to the loaded label file
            # overlay:    Overlay to apply them to
            # allLabels:  Loaded labels (list of (component, [label]) tuples)
            # newOverlay: True if the selected overlay has changed, False
            #             otherwise

            lut      = self.__lut
            melclass = overlay.getICClassification()

            ncomps  = overlay.numComponents()
            nlabels = len(allLabels)

            # Error: number of labels in the
            # file is greater than the number
            # of components in the overlay.
            if ncomps < nlabels:
                msg   = strings.messages[self, 'wrongNComps'].format(
                    labelFile, overlay.dataSource)
                title = strings.titles[  self, 'loadError']
                wx.MessageBox(msg, title, wx.ICON_ERROR | wx.OK)                
                return

            # Number of labels in the file is
            # less than number of components
            # in the overlay - we pad the
            # labels with 'Unknown'
            elif ncomps > nlabels:
                for i in range(nlabels, ncomps):
                    allLabels.append(['Unknown'])

            # Disable notification while applying
            # labels so the component/label grids
            # don't confuse themselves.
            with melclass.skip(self.__componentGrid._name), \
                 melclass.skip(self.__labelGrid    ._name):

                melclass.clear()

                for comp, lbls in enumerate(allLabels):
                    for lbl in lbls:
                        melclass.addLabel(comp, lbl)

                # Make sure a colour in the melodic
                # lookup table exists for all labels
                for label in melclass.getAllLabels():

                    label    = melclass.getDisplayLabel(label)
                    lutLabel = lut.getByName(label)

                    if lutLabel is None:
                        log.debug('New melodic classification '
                                  'label: {}'.format(label))
                        lut.new(label, colour=fslcm.randomBrightColour())

            # New overlay was loaded
            if newOverlay:

                # Make sure the new image is selected. 
                with props.skip(self._displayCtx,
                                'selectedOverlay',
                                self._name):
                    self._displayCtx.selectOverlay(overlay)

                self.__componentGrid.setOverlay(overlay)
                self.__labelGrid    .setOverlay(overlay)

            # Labels were applied to
            # already selected overlay.
            else:
                self.__componentGrid.refreshTags()
                self.__labelGrid    .refreshTags()

        # If the current overlay is a MelodicImage,
        # the open file dialog starting point will
        # be the melodic directory.
        overlay           = self._displayCtx.getSelectedOverlay()
        selectedIsMelodic = isinstance(overlay, fslmelimage.MelodicImage)
        
        if selectedIsMelodic:
            loadDir = overlay.getMelodicDir()

        # Otherwise it will be the most
        # recent overlay load directory.
        else:
            loadDir = fslsettings.read('loadSaveOverlayDir', os.getcwd())

        # Ask the user to select a label file
        dlg = wx.FileDialog(
            self,
            message=strings.titles[self, 'loadDialog'],
            defaultDir=loadDir,
            style=wx.FD_OPEN)

        # User cancelled the dialog
        if dlg.ShowModal() != wx.ID_OK:
            return

        # Load the specified label file
        filename = dlg.GetPath()
        try:
            melDir, allLabels = fslmellabels.loadLabelFile(filename)

        # Problem loading the file
        except Exception as e:
            
            e     = str(e)
            msg   = strings.messages[self, 'loadError'].format(filename, e)
            title = strings.titles[  self, 'loadError']
            log.warning('Error loading classification file '
                      '({}), ({})'.format(filename, e), exc_info=True)
            wx.MessageBox(msg, title, wx.ICON_ERROR | wx.OK)

            return

        # Ok we've got the labels, now
        # we need to figure out which
        # overlay to add them to.

        # If the label file does not refer
        # to a Melodic directory, and the
        # current overlay is a melodic
        # image, apply the labels to the image.
        if selectedIsMelodic and (melDir is None):
            applyLabels(filename, overlay, allLabels, False)
            return

        # If the label file refers to a
        # Melodic directory, and the
        # current overlay is a melodic
        # image.
        if selectedIsMelodic and (melDir is not None):

            overlayDir = overlay.getMelodicDir()

            # And both the current overlay and
            # the label file refer to the same
            # melodic directory, then we apply
            # the labels to the curent overlay.
            if op.abspath(melDir) == op.abspath(overlayDir):

                applyLabels(filename, overlay, allLabels, False)
                return
            
            # Otherwise, if the overlay and the
            # label file refer to different
            # melodic directories...

            # Ask the user whether they want to load
            # the image specified in the label file,
            # or apply the labels to the currently
            # selected meldic image.
            dlg = wx.MessageDialog(
                self,
                strings.messages[self, 'diffMelDir'].format(
                    melDir, overlayDir),
                style=wx.ICON_QUESTION | wx.YES_NO | wx.CANCEL)
            dlg.SetYesNoLabels(
                strings.messages[self, 'diffMelDir.labels'],
                strings.messages[self, 'diffMelDir.overlay'])

            response = dlg.ShowModal()

            # User cancelled the dialog
            if response == wx.ID_CANCEL:
                return

            # User chose to load the melodic
            # image specified in the label
            # file. We'll carry on with this
            # processing below.
            elif response == wx.ID_YES:
                pass

            # Apply the labels to the current
            # overlay, even though they are
            # from different analyses.
            else:
                applyLabels(filename, overlay, allLabels, False)
                return

        # If we've reached this far, we are
        # going to attempt to identify the
        # melodic image associated with the
        # label file, load that image, and
        # then apply the labels.
        
        # The label file does not
        # specify a melodic directory
        if melDir is None:

            msg   = strings.messages[self, 'noMelDir'].format(filename)
            title = strings.titles[  self, 'loadError']
            wx.MessageBox(msg, title, wx.ICON_ERROR | wx.OK)
            return

        # Try loading the melodic_IC image
        # specified in the label file. 
        try:
            overlay = fslmelimage.MelodicImage( melDir)

            log.debug('Adding {} to overlay list'.format(overlay))

            with props.skip(self._overlayList, 'overlays',        self._name),\
                 props.skip(self._displayCtx,  'selectedOverlay', self._name):
            
                self._overlayList.append(overlay)

            if self._displayCtx.autoDisplay:
                autodisplay.autoDisplay(overlay,
                                        self._overlayList,
                                        self._displayCtx)

            fslsettings.write('loadSaveOverlayDir', op.abspath(melDir)) 

        except Exception as e:

            e     = str(e)
            msg   = strings.messages[self, 'loadError'].format(filename, e)
            title = strings.titles[  self, 'loadError']
            log.debug('Error loading classification file '
                      '({}), ({})'.format(filename, e), exc_info=True)
            wx.MessageBox(msg, title, wx.ICON_ERROR | wx.OK)

        # Apply the loaded labels
        # to the loaded overlay.
        applyLabels(filename, overlay, allLabels, True)

    
    def __onSaveButton(self, ev):
        """Called when the user pushe the *Save labels* button. Asks the user
        where they'd like the label saved, then saves said labels.
        """

        overlay  = self._displayCtx.getSelectedOverlay()
        melclass = overlay.getICClassification()
        dlg      = wx.FileDialog(
            self,
            message=strings.titles[self, 'saveDialog'],
            defaultDir=overlay.getMelodicDir(),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        
        if dlg.ShowModal() != wx.ID_OK:
            return

        filename = dlg.GetPath()

        try:
            melclass.save(filename)
            
        except Exception as e:
            e     = str(e)
            msg   = strings.messages[self, 'saveError'].format(filename, e)
            title = strings.titles[  self, 'saveError']
            log.debug('Error saving classification file '
                      '({}), ({})'.format(filename, e), exc_info=True)
            wx.MessageBox(msg, title, wx.ICON_ERROR | wx.OK) 

    
    def __onClearButton(self, ev):
        """Called when the user pushes the *Clear labels* button. Resets
        all of the labels (sets the label for every component to
        ``'Unknown'``).
        """
        
        overlay  = self._displayCtx.getSelectedOverlay()
        melclass = overlay.getICClassification()

        for c in range(overlay.numComponents()):

            labels = melclass.getLabels(c)

            if len(labels) == 1 and labels[0] == 'unknown':
                continue

            melclass.clearLabels(c)
            melclass.addLabel(c, 'Unknown')
