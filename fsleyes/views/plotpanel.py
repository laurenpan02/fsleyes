#!/usr/bin/env python
#
# plotpanel.py - The PlotPanel class.
#
# Author: Paul McCarthy <pauldmccarthy@gmail.com>
#
"""This module provides the :class:`PlotPanel` and :class:`.OverlayPlotPanel`
classes.  The ``PlotPanel`` class is the base class for all *FSLeyes views*
which display some sort of data plot. The ``OverlayPlotPanel`` is a
``PlotPanel`` which contains some extra logic for displaying plots related to
the currently selected overlay.
"""


import logging

import wx

import matplotlib        as mpl
import numpy             as np
import scipy.interpolate as interp


mpl.use('WxAgg')


import matplotlib.pyplot as plt

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as Canvas
from matplotlib.backends.backend_wx    import NavigationToolbar2Wx


import                                       props
import pwidgets.elistbox                  as elistbox
import fsl.utils.async                    as async
import fsl.data.image                     as fslimage
import fsleyes.strings                    as strings
import fsleyes.actions                    as actions
import fsleyes.overlay                    as fsloverlay
import fsleyes.colourmaps                 as fslcm
import fsleyes.plotting                   as plotting
import fsleyes.controls.overlaylistpanel  as overlaylistpanel
import fsleyes.controls.plotlistpanel     as plotlistpanel
from . import                                viewpanel


log = logging.getLogger(__name__)


class PlotPanel(viewpanel.ViewPanel):
    """The ``PlotPanel`` class is the base class for all *FSLeyes views*
    which display some sort of 2D data plot, such as the
    :class:`.TimeSeriesPanel`, and the :class:`.HistogramPanel`. 
    See also the :class:`OverlayPlotPanel`, which contains extra logic for
    displaying plots related to the currently selected overlay.

    
    ``PlotPanel`` uses :mod:`matplotlib` for its plotting. The ``matplotlib``
    ``Figure``, ``Axis``, and ``Canvas`` instances can be accessed via the
    :meth:`getFigure`, :meth:`getAxis`, and :meth:`getCanvas` methods, if they
    are needed. Various display settings can be configured through
    ``PlotPanel`` properties, including :attr:`legend`, :attr:`smooth`, etc.

    
    **Sub-class requirements**

    Sub-class implementations of ``PlotPanel`` must do the following:

      1. Call the ``PlotPanel`` constructor.

      2. Define a :class:`.DataSeries` sub-class.

      3. Override the :meth:`draw` method, so it calls the
         :meth:`drawDataSeries` method.

      4. If necessary, override the :meth:`prepareDataSeries` method to
         perform any preprocessing on ``extraSeries`` passed to the
         :meth:`drawDataSeries` method (but not applied to
         :class:`.DataSeries` that have been added to the :attr:`dataSeries`
         list).

      5. If necessary, override the :meth:`destroy` method, but make
         sure that the base-class implementation is called.

    
    **Data series**

    A ``PlotPanel`` instance plots data contained in one or more
    :class:`.DataSeries` instances; all ``DataSeries`` classes are defined in
    the :mod:`.plotting` sub-package.  Therefore, ``PlotPanel`` sub-classes
    also need to define a sub-class of the :class:`.DataSeries` base class.

    ``DataSeries`` objects can be plotted by passing them to the
    :meth:`drawDataSeries` method.

    Or, if you want one or more ``DataSeries`` to be *held*, i.e. plotted
    every time, you can add them to the :attr:`dataSeries` list. The
    ``DataSeries`` in the :attr:`dataSeries` list will be plotted on every
    call to :meth:`drawDataSeries` (in addition to any ``DataSeries`` passed
    directly to :meth:`drawDataSeries`) until they are removed from the
    :attr:`dataSeries` list.


    **Plot panel actions**

    A number of :mod:`actions` are also provided by the ``PlotPanel`` class:

    .. autosummary::
       :nosignatures:

       screenshot
       importDataSeries
       exportDataSeries
    """


    dataSeries = props.List()
    """This list contains :class:`.DataSeries` instances which are plotted
    on every call to :meth:`drawDataSeries`. ``DataSeries`` instances can
    be added/removed directly to/from this list.
    """

    
    legend = props.Boolean(default=True)
    """If ``True``, a legend is added to the plot, with an entry for every
    ``DataSeries`` instance in the :attr:`dataSeries` list.
    """


    xAutoScale = props.Boolean(default=True)
    """If ``True``, the plot :attr:`limits` for the X axis are automatically 
    updated to fit all plotted data.
    """

    
    yAutoScale = props.Boolean(default=True)
    """If ``True``, the plot :attr:`limits` for the Y axis are automatically 
    updated to fit all plotted data.
    """

    
    xLogScale = props.Boolean(default=False)
    """Toggle a :math:`log_{10}` x axis scale. """

    
    yLogScale = props.Boolean(default=False)
    """Toggle a :math:`log_{10}` y axis scale. """

    
    ticks = props.Boolean(default=True)
    """Toggle axis ticks and tick labels on/off."""

    
    grid = props.Boolean(default=True)
    """Toggle an axis grid on/off."""


    gridColour = props.Colour(default=(1, 1, 1))
    """Grid colour (if :attr:`grid` is ``True``)."""


    bgColour = props.Colour(default=(0.8, 0.8, 0.8))
    """Plot background colour."""

    
    smooth = props.Boolean(default=False)
    """If ``True`` all plotted data is up-sampled, and smoothed using
    spline interpolation.
    """

    
    xlabel = props.String()
    """A label to show on the x axis. """

    
    ylabel = props.String()
    """A label to show on the y axis. """

    
    limits = props.Bounds(ndims=2)
    """The x/y axis limits. If :attr:`xAutoScale` and :attr:`yAutoScale` are
    ``True``, these limit values are automatically updated on every call to
    :meth:`drawDataSeries`.
    """

    
    def __init__(self,
                 parent,
                 overlayList,
                 displayCtx,
                 interactive=True):
        """Create a ``PlotPanel``.

        :arg parent:      The :mod:`wx` parent object.
        
        :arg overlayList: An :class:`.OverlayList` instance.
        
        :arg displayCtx:  A :class:`.DisplayContext` instance.
        
        :arg interactive: If ``True`` (the default), the canvas is configured
                          so the user can pan/zoom the plot with the mouse.
        """
         
        viewpanel.ViewPanel.__init__(
            self, parent, overlayList, displayCtx)

        figure = plt.Figure()
        axis   = figure.add_subplot(111)
        canvas = Canvas(self, -1, figure)

        figure.subplots_adjust(top=1.0, bottom=0.0, left=0.0, right=1.0)
        figure.patch.set_visible(False)
        
        self.setCentrePanel(canvas)

        self.__figure    = figure
        self.__axis      = axis
        self.__canvas    = canvas
        self.__name      = 'PlotPanel_{}'.format(self._name)

        # Accessing data from large compressed
        # files may take time, so we maintain
        # a queue of plotting requests. The
        # functions executed on this task
        # thread are used to prepare data for
        # plotting - the plotting occurs on
        # the main WX event loop.
        #
        # The drawDataSeries method sets up the
        # asynchronous data preparation, and the
        # __drawDataSeries method does the actual
        # plotting.
        self.__drawQueue = async.TaskThread()
        self.__drawQueue.daemon = True
        self.__drawQueue.start()

        # Whenever a new request comes in to
        # draw the plot, we can't cancel any
        # pending requests, as they are running
        # on separate threads and out of our
        # control (and could be blocking on I/O).
        # 
        # Instead, we keep track of the total
        # number of pending requests. The
        # __drawDataSeries method (which does the
        # actual plotting) will only draw the
        # plot if there are no pending requests
        # (because otherwise it would be drawing
        # out-of-date data).
        self.__drawRequests = 0

        if interactive:
            
            # Pan/zoom functionality is implemented
            # by the NavigationToolbar2Wx, but the
            # toolbar is not actually shown.
            self.__mouseDown = False
            self.__toolbar = NavigationToolbar2Wx(canvas)
            self.__toolbar.Show(False)
            self.__toolbar.pan()
            
            canvas.mpl_connect('button_press_event',   self.__onMouseDown)
            canvas.mpl_connect('motion_notify_event',  self.__onMouseMove)
            canvas.mpl_connect('button_release_event', self.__onMouseUp)
            canvas.mpl_connect('axes_leave_event',     self.__onMouseUp)

        # Redraw whenever any property changes, 
        for propName in ['legend',
                         'xAutoScale',
                         'yAutoScale',
                         'xLogScale',
                         'yLogScale',
                         'ticks',
                         'grid',
                         'gridColour',
                         'bgColour',
                         'smooth',
                         'xlabel',
                         'ylabel']:
            self.addListener(propName, self.__name, self.asyncDraw)
            
        # custom listeners for a couple of properties
        self.addListener('dataSeries',
                         self.__name,
                         self.__dataSeriesChanged)
        self.addListener('limits',
                         self.__name,
                         self.__limitsChanged)


    def getFigure(self):
        """Returns the ``matplotlib`` ``Figure`` instance."""
        return self.__figure
    

    def getAxis(self):
        """Returns the ``matplotlib`` ``Axis`` instance."""
        return self.__axis


    def getCanvas(self):
        """Returns the ``matplotlib`` ``Canvas`` instance."""
        return self.__canvas


    def draw(self, *a):
        """This method must be overridden by ``PlotPanel`` sub-classes.

        It is called whenever a :class:`.DataSeries` is added to the
        :attr:`dataSeries` list, or when any plot display properties change.

        Sub-class implementations should call the :meth:`drawDataSeries`
        method.
        """
        raise NotImplementedError('The draw method must be '
                                  'implemented by PlotPanel subclasses')


    def asyncDraw(self, *a):
        """Schedules :meth:`draw` to be run asynchronously. This method
        should be used in preference to calling :meth:`draw` directly
        in most cases, particularly where the call occurs within a
        property callback function.
        """

        idleName = '{}.draw'.format(id(self))

        if not self.destroyed() and not async.inIdle(idleName):
            async.idle(self.draw, name=idleName)
    
        
    def destroy(self):
        """Removes some property listeners, and then calls
        :meth:`.ViewPanel.destroy`.
        """

        self.__drawQueue.stop()
        self.__drawQueue = None
        
        self.removeListener('dataSeries', self.__name)
        self.removeListener('limits',     self.__name)
        
        for propName in ['legend',
                         'xAutoScale',
                         'yAutoScale',
                         'xLogScale',
                         'yLogScale',
                         'ticks',
                         'grid',
                         'gridColour',
                         'bgColour',
                         'smooth',
                         'xlabel',
                         'ylabel']:
            self.removeListener(propName, self.__name)
            
        for ds in self.dataSeries:
            ds.removeGlobalListener(self.__name)
            ds.destroy()

        self.dataSeries = []
            
        viewpanel.ViewPanel.destroy(self)


    @actions.action
    def screenshot(self, *a):
        """Prompts the user to select a file name, then saves a screenshot
        of the current plot.
        """

        formats  = self.__canvas.get_supported_filetypes().items()

        wildcard = ['{}|*.{}'.format(desc, fmt) for fmt, desc in formats]
        wildcard = '|'.join(wildcard)

        dlg = wx.FileDialog(self,
                            message=strings.messages[self, 'screenshot'],
                            wildcard=wildcard,
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)

        if dlg.ShowModal() != wx.ID_OK:
            return

        path = dlg.GetPath()

        try:
            self.__figure.savefig(path)
            
        except Exception as e:
            wx.MessageBox(
                strings.messages[self, 'screenshot', 'error'].format(str(e)),
                strings.titles[  self, 'screenshot', 'error'],
                wx.ICON_ERROR)


    # @actions.action
    def importDataSeries(self, *a):
        """Not implemented yet. Imports data series from a text file."""
        pass


    # @actions.action
    def exportDataSeries(self, *a):
        """Not implemented yet. Exports displayed data series to a text file.
        """
        pass
            

    def message(self, msg, clear=True, border=False):
        """Displays the given message in the centre of the figure.

        This is a convenience method provided for use by subclasses.
        """

        axis = self.getAxis()

        if clear:
            axis.clear()
            axis.set_xlim((0.0, 1.0))
            axis.set_ylim((0.0, 1.0))

        if border:
            bbox = {'facecolor' : '#ffffff',
                    'edgecolor' : '#cdcdff',
                    'boxstyle'  : 'round,pad=1'}
        else:
            bbox = None

        axis.text(0.5, 0.5,
                  msg,
                  ha='center', va='center',
                  transform=axis.transAxes,
                  bbox=bbox)
        
        self.getCanvas().draw()
        self.Refresh()


    def prepareDataSeries(self, ds):
        """Prepares the data from the given :class:`.DataSeries` so it is
        ready to be plotted. Called by the :meth:`__drawOneDataSeries` method
        for any ``extraSeries`` passed to the :meth:`drawDataSeries` method
        (but not applied to :class:`.DataSeries` that have been added to the
        :attr:`dataSeries` list).

        This implementation just returns :class:`.DataSeries.getData` -
        override it to perform any custom preprocessing.
        """
        return ds.getData()


    def drawDataSeries(self, extraSeries=None, **plotArgs):
        """Queues a request to plot all of the :class:`.DataSeries` instances
        in the :attr:`dataSeries` list.

        This method does not do the actual plotting - it is performed
        asynchronously, to avoid locking up the GUI:

         1. The data for each ``DataSeries`` instance is prepared on
            separate threads (using :func:`.async.run`).
        
         2. A call to :func:`.async.wait` is enqueued on a
            :class:`.TaskThread`.

         3. This ``wait`` function waits until all of the data preparation
            threads have completed, and then passes all of the data to
            the :meth:`__drawDataSeries` method.

        :arg extraSeries: A sequence of additional ``DataSeries`` to be
                          plotted. These series are passed through the
                          :meth:`prepareDataSeries` method before being
                          plotted.

        :arg plotArgs:    Passed through to the :meth:`__drawDataSeries`
                          method.

        
        .. note:: This method must only be called from the main application
                  thread (the ``wx`` event loop).
        """

        if extraSeries is None:
            extraSeries = []

        canvas   = self.getCanvas()
        axis     = self.getAxis()
        toPlot   = self.dataSeries[:]
        toPlot   = extraSeries + toPlot
        preprocs = [True] * len(extraSeries) + [False] * len(toPlot)

        if len(toPlot) == 0:
            axis.clear()
            canvas.draw()
            self.Refresh()
            return

        # Before clearing/redrawing, save
        # a copy of the x/y axis limits -
        # the user may have changed them
        # via panning/zooming and, if
        # autoLimit is off, we will want
        # to preserve the limits that the
        # user set. These are passed to
        # the __drawDataSeries method.
        axxlim = axis.get_xlim()
        axylim = axis.get_ylim()

        # Here we are preparing the data for
        # each data series on separate threads,
        # as data preparation can be time
        # consuming for large images. We
        # display a message on the canvas
        # during preparation.
        tasks    = []
        allXdata = [None] * len(toPlot)
        allYdata = [None] * len(toPlot)

        # Create a separate function
        # for each data series
        for idx, (ds, preproc) in enumerate(zip(toPlot, preprocs)):

            def getData(d=ds, p=preproc, i=idx):

                if not d.enabled:
                    return
                
                if p: xdata, ydata = self.prepareDataSeries(d)
                else: xdata, ydata = d.getData()

                allXdata[i] = xdata
                allYdata[i] = ydata

            tasks.append(getData)

        # Run the data preparation tasks,
        # a separate thread for each.
        tasks = [async.run(t) for t in tasks]

        # Show a message while we're
        # preparing the data.
        self.message(strings.messages[self, 'preparingData'],
                     clear=False,
                     border=True)

        # Wait until data preparation is
        # done, then call __drawDataSeries.
        self.__drawRequests += 1
        self.__drawQueue.enqueue('{}.wait'.format(id(self)),
                                 async.wait,
                                 tasks,
                                 self.__drawDataSeries,
                                 toPlot,
                                 allXdata,
                                 allYdata,
                                 axxlim,
                                 axylim,
                                 wait_direct=True,
                                 **plotArgs) 
        

    def __drawDataSeries(
            self,
            dataSeries,
            allXdata,
            allYdata,
            oldxlim,
            oldylim,
            **plotArgs):
        """Called by :meth:`__drawDataSeries`. Plots all of the data
        associated with the given ``dataSeries``.

        :arg dataSeries: The list of :class:`.DataSeries` instances to plot.
        
        :arg allXdata:   A list of arrays containing X axis data, one for each
                         ``DataSeries``.
        
        :arg allYdata:   A list of arrays containing Y axis data, one for each
                         ``DataSeries``.
        
        :arg oldxlim:    X plot limits from the previous draw. If
                         ``xAutoScale`` is disabled, this limit is preserved.
        
        :arg oldylim:    Y plot limits from the previous draw. If
                         ``yAutoScale`` is disabled, this limit is preserved.
        
        :arg plotArgs:   Remaining arguments passed to the
                         :meth:`__drawOneDataSeries` method.
        """
        
        # Only draw the plot if there are no
        # pending draw requests. Otherwise
        # we would be drawing out-of-date data.
        self.__drawRequests -= 1
        if self.__drawRequests != 0:
            return
        
        axis          = self.getAxis()
        canvas        = self.getCanvas()
        width, height = canvas.get_width_height()
        axis.clear()

        xlims = []
        ylims = []
        
        for ds, xdata, ydata in zip(dataSeries, allXdata, allYdata):

            if any((ds is None, xdata is None, ydata is None)):
                continue

            if not ds.enabled:
                continue

            xlim, ylim = self.__drawOneDataSeries(ds,
                                                  xdata,
                                                  ydata,
                                                  **plotArgs)

            if np.any(np.isclose([xlim[0], ylim[0]], [xlim[1], ylim[1]])):
                continue

            xlims.append(xlim)
            ylims.append(ylim)

        if len(xlims) == 0:
            xmin, xmax = 0.0, 0.0
            ymin, ymax = 0.0, 0.0
        else:
            (xmin, xmax), (ymin, ymax) = self.__calcLimits(
                xlims, ylims, oldxlim, oldylim, width, height)

        # x/y axis labels
        xlabel = self.xlabel 
        ylabel = self.ylabel

        if xlabel is None: xlabel = ''
        if ylabel is None: ylabel = ''

        xlabel = xlabel.strip()
        ylabel = ylabel.strip()

        if xlabel != '':
            axis.set_xlabel(self.xlabel, va='bottom')
            axis.xaxis.set_label_coords(0.5, 10.0 / height)
            
        if ylabel != '':
            axis.set_ylabel(self.ylabel, va='top')
            axis.yaxis.set_label_coords(10.0 / width, 0.5)

        # Ticks
        if self.ticks:
            axis.tick_params(direction='in', pad=-5)

            for ytl in axis.yaxis.get_ticklabels():
                ytl.set_horizontalalignment('left')
                
            for xtl in axis.xaxis.get_ticklabels():
                xtl.set_verticalalignment('bottom')
        else:
            axis.set_xticks([])
            axis.set_yticks([])

        # Limits
        if xmin != xmax:
            axis.set_xlim((xmin, xmax))
            axis.set_ylim((ymin, ymax))

        # legend
        labels = [ds.label for ds in dataSeries if ds.label is not None]
        if len(labels) > 0 and self.legend:
            handles, labels = axis.get_legend_handles_labels()
            legend          = axis.legend(
                handles,
                labels,
                loc='upper right',
                fontsize=12,
                fancybox=True)
            legend.get_frame().set_alpha(0.6)

        if self.grid:
            axis.grid(linestyle='-',
                      color=self.gridColour,
                      linewidth=2,
                      zorder=0)
        else:
            axis.grid(False)

        axis.set_axisbelow(True)
        axis.patch.set_facecolor(self.bgColour)
        self.getFigure().patch.set_alpha(0)

        canvas.draw()
        self.Refresh()

        
    def __drawOneDataSeries(self, ds, xdata, ydata, **plotArgs):
        """Plots a single :class:`.DataSeries` instance. This method is called
        by the :meth:`drawDataSeries` method.

        :arg ds:       The ``DataSeries`` instance.
        :arg xdata:    X axis data.
        :arg ydata:    Y axis data.
        :arg plotArgs: May be used to customise the plot - these
                       arguments are all passed through to the
                       ``Axis.plot`` function.
        """
        
        if ds.alpha == 0:
            return (0, 0), (0, 0)

        if len(xdata) != len(ydata) or len(xdata) == 0:
            return (0, 0), (0, 0)

        log.debug('Drawing {} for {}'.format(type(ds).__name__, ds.overlay))

        # Note to self: If the smoothed data is
        # filled with NaNs, it is possibly due
        # to duplicate values in the x data, which
        # are not handled very well by splrep.
        if self.smooth:

            tck   = interp.splrep(xdata, ydata)
            xdata = np.linspace(xdata[0],
                                xdata[-1],
                                len(xdata) * 5,
                                dtype=np.float32)
            ydata = interp.splev(xdata, tck)

        nans        = ~(np.isfinite(xdata) & np.isfinite(ydata))
        xdata[nans] = np.nan
        ydata[nans] = np.nan

        if self.xLogScale: xdata[xdata <= 0] = np.nan
        if self.yLogScale: ydata[ydata <= 0] = np.nan

        if np.all(np.isnan(xdata) | np.isnan(ydata)):
            return (0, 0), (0, 0)

        kwargs = plotArgs

        kwargs['lw']    = kwargs.get('lw',    ds.lineWidth)
        kwargs['alpha'] = kwargs.get('alpha', ds.alpha)
        kwargs['color'] = kwargs.get('color', ds.colour)
        kwargs['label'] = kwargs.get('label', ds.label)
        kwargs['ls']    = kwargs.get('ls',    ds.lineStyle)

        axis = self.getAxis()

        axis.plot(xdata, ydata, **kwargs)

        if self.xLogScale:
            axis.set_xscale('log')
            posx    = xdata[xdata > 0]
            xlimits = np.nanmin(posx), np.nanmax(posx)
            
        else:
            xlimits = np.nanmin(xdata), np.nanmax(xdata)
            
        if self.yLogScale:
            axis.set_yscale('log')
            posy    = ydata[ydata > 0]
            ylimits = np.nanmin(posy), np.nanmax(posy)
        else:
            ylimits = np.nanmin(ydata), np.nanmax(ydata)
            
        return xlimits, ylimits

    
    def __onMouseDown(self, ev):
        """Sets a flag so the :meth:`__onMouseMove` method knows that the
        mouse is down.
        """
        self.__mouseDown = True

        
    def __onMouseUp(self, ev):
        """Sets a flag so the :meth:`__onMouseMove` method knows that the
        mouse is up.
        """ 
        self.__mouseDown = False

        
    def __onMouseMove(self, ev):
        """If this ``PlotPanel`` is interactive (determined by the
        ``interactive`` parameter to :meth:`__init__`), mouse drags will
        change the axis limits.

        This behaviour is provided by ``matplotlib`` - this method simply
        makes sure that the :attr:`limits` property is up to date.
        """

        if not self.__mouseDown:
            return

        xlims = list(self.__axis.get_xlim())
        ylims = list(self.__axis.get_ylim())

        self.disableListener('limits', self.__name)
        self.limits.x = xlims
        self.limits.y = ylims
        self.enableListener( 'limits', self.__name)


    def __dataSeriesChanged(self, *a):
        """Called when the :attr:`dataSeries` list changes. Adds listeners
        to any new :class:`.DataSeries` instances, and then calls :meth:`draw`.
        """
        
        for ds in self.dataSeries:
            ds.addGlobalListener(self.__name, self.asyncDraw, overwrite=True)
        self.asyncDraw()


    def __limitsChanged(self, *a):
        """Called when the :attr:`limits` change. Updates the axis limits
        accordingly.
        """

        axis = self.getAxis()
        axis.set_xlim(self.limits.x)
        axis.set_ylim(self.limits.y)
        self.asyncDraw()

        
    def __calcLimits(self,
                     dataxlims,
                     dataylims,
                     axisxlims,
                     axisylims,
                     axWidth,
                     axHeight):
        """Calculates and returns suitable axis limits for the current plot.
        Also updates the :attr:`limits` property. This method is called by
        the :meth:`drawDataSeries` method.

        If :attr:`xAutoScale` or :attr:`yAutoScale` are enabled, the limits are
        calculated from the data range, using the canvas width and height to
        maintain consistent padding around the plotted data, irrespective of
        the canvas size.

        . Otherwise, the existing axis limits are retained.

        :arg dataxlims: A tuple containing the (min, max) x data range.
        
        :arg dataylims: A tuple containing the (min, max) y data range.
        
        :arg axisxlims: A tuple containing the current (min, max) x axis
                        limits.
        
        :arg axisylims: A tuple containing the current (min, max) y axis
                        limits.
        
        :arg axWidth:   Canvas width in pixels
        
        :arg axHeight:  Canvas height in pixels
        """

        if self.xAutoScale:

            xmin = min([lim[0] for lim in dataxlims])
            xmax = max([lim[1] for lim in dataxlims])
            
            lPad = (xmax - xmin) * (50.0 / axWidth)
            rPad = (xmax - xmin) * (50.0 / axWidth)

            xmin = xmin - lPad
            xmax = xmax + rPad 
        else:
            xmin = axisxlims[0]
            xmax = axisxlims[1] 

        if self.yAutoScale:
            
            ymin = min([lim[0] for lim in dataylims])
            ymax = max([lim[1] for lim in dataylims])
            
            bPad = (ymax - ymin) * (50.0 / axHeight)
            tPad = (ymax - ymin) * (50.0 / axHeight)

            ymin = ymin - bPad
            ymax = ymax + tPad 
            
        else:

            ymin = axisylims[0]
            ymax = axisylims[1]

        self.disableListener('limits', self.__name)
        self.limits[:] = [xmin, xmax, ymin, ymax]
        self.enableListener('limits', self.__name)            
 
        return (xmin, xmax), (ymin, ymax)


class OverlayPlotPanel(PlotPanel):
    """The ``OverlayPlotPanel`` is a :class:`.PlotPanel` which contains
    some extra logic for creating and storing :class:`.DataSeries`
    instances for each overlay in the :class:`.OverlayList`.


    **Subclass requirements**

    Sub-classes must:

     1. Implement the :meth:`createDataSeries` method, so it creates a
        :class:`.DataSeries` instance for a specified overlay.

     2. Implement the :meth:`PlotPanel.draw` method so it honours the
        current value of the :attr:`showMode` property.

     3. Optionally implement the :meth:`prepareDataSeries` method to
        perform any custom preprocessing.

    
    **The internal data series store**


    The ``OverlayPlotPanel`` maintains a store of :class:`.DataSeries`
    instances, one for each compatible overlay in the
    :class:`.OverlayList`. The ``OverlayPlotPanel`` manages the property
    listeners that must be registered with each of these ``DataSeries`` to
    refresh the plot.  These instances are created by the
    :meth:`createDataSeries` method, which is implemented by sub-classes. The
    following methods are available to sub-classes, for managing the internal
    store of :class:`.DataSeries` instances:

    .. autosummary::
       :nosignatures:

       getDataSeries
       clearDataSeries
       updateDataSeries
       addDataSeries
       removeDataSeries

    
    **The current data series**

    
    By default, the ``OverlayPlotPanel`` plots the data series associated with
    the currently selected overlay, which is determined from the
    :attr:`.DisplayContext.selectedOverlay`. This data series is referred to
    as the *current* data series. The :attr:`showMode` property allows the
    user to choose between showing only the current data series, showing the
    data series for all (compatible) overlays, or only showing the data series
    that have been added to the :attr:`.PlotPanel.dataSeries` list.  Other
    data series can be *held* by adding them to the
    :attr:`.PlotPanel.dataSeries` list.


    **Proxy images**

    
    The ``OverlayPlotPanel`` will replace all :class:`.ProxyImage` instances
    with their base images. This functionality was originally added to support
    the :attr:`.HistogramSeries.showOverlay` functionality - it adds a mask
    image to the :class:`.OverlayList` to display the histogram range.
    Sub-classes may wish to adhere to the same logic (replacing ``ProxyImage``
    instances with their bases)


    **Control panels**


    The :class:`.PlotControlPanel` and :class:`.PlotListPanel` are *FSLeyes
    control* panels which work with the :class:`.OverlayPlotPanel`.

    
    The ``OverlayPlotPanel`` is the base class for:

    .. autosummary::
       :nosignatures:

       ~fsleyes.views.timeseriespanel.TimeSeriesPanel
       ~fsleyes.views.histogrampanel.HistogramPanel
       ~fsleyes.views.powerspectrumpanel.PowerSpectrumPanel
    """

    
    showMode = props.Choice(('all', 'current', 'none'))
    """Defines which data series to plot.

    =========== =====================================================
    ``all``     The data series for all compatible overlays in the 
                :class:`.OverlayList` are plotted.
    ``current`` The data series for the currently selected overlay is
                plotted.
    ``none``    Only the ``DataSeries`` that are in the
                :attr:`.PlotPanel.dataSeries` list will be plotted.
    =========== =====================================================
    """

    
    plotColours = {}
    """This dictionary is used to store a collection of ``{overlay : colour}``
    mappings. It is shared across all ``OverlayPlotPanel`` instances, so that
    the same (initial) colour is used for the same overlay, across multiple
    plots.
    
    Sub-classes should use the :meth:`getOverlayPlotColour` method to retrieve
    the initial colour to use for a given overlay.
    """


    def __init__(self, *args, **kwargs):
        """Create an ``OverlayPlotPanel``. All argumenst are passed through to 
        :meth:`PlotPanel.__init__`.
        """

        PlotPanel.__init__(self, *args, **kwargs)
        
        self.__name = 'OverlayPlotPanel_{}'.format(self._name)

        # The dataSeries attribute is a dictionary of
        #
        #   {overlay : DataSeries}
        #
        # mappings, containing a DataSeries instance for
        # each compatible overlay in the overlay list.
        # 
        # Different DataSeries types need to be re-drawn
        # when different properties change. For example,
        # a TimeSeries instance needs to be redrawn when
        # the DisplayContext.location property changes,
        # whereas a MelodicTimeSeries instance needs to
        # be redrawn when the VolumeOpts.volume property
        # changes.
        #
        # Therefore, the refreshProps dictionary contains
        # a set of
        #
        #   {overlay : ([targets], [propNames])}
        #
        # mappings - for each overlay, a list of
        # target objects (e.g. DisplayContext, VolumeOpts,
        # etc), and a list of property names on each,
        # defining the properties that need to trigger a
        # redraw.
        #
        # See the createDataSeries method for more
        # information.
        self.__dataSeries   = {}
        self.__refreshProps = {}

        self             .addListener('showMode',
                                      self.__name,
                                      self.__showModeChanged)
        self             .addListener('dataSeries',
                                      self.__name,
                                      self.__dataSeriesChanged) 
        self._displayCtx .addListener('selectedOverlay',
                                      self.__name,
                                      self.__selectedOverlayChanged)
        self._overlayList.addListener('overlays',
                                      self.__name,
                                      self.__overlayListChanged)

        self.__overlayListChanged()
        self.__dataSeriesChanged()


    def destroy(self):
        """Must be called when this ``OverlayPlotPanel`` is no longer needed.
        Removes some property listeners, and calls :meth:`PlotPanel.destroy`.
        """
        self             .removeListener('showMode',        self.__name)
        self._overlayList.removeListener('overlays',        self.__name)
        self._displayCtx .removeListener('selectedOverlay', self.__name)

        for overlay in list(self.__dataSeries.keys()):
            self.clearDataSeries(overlay)

        self.__dataSeries   = None
        self.__refreshProps = None

        PlotPanel.destroy(self)
        

    def getDataSeries(self, overlay):
        """Returns the :class:`.DataSeries` instance associated with the
        specified overlay, or ``None`` if there is no ``DataSeries`` instance.
        """
        
        if isinstance(overlay, fsloverlay.ProxyImage):
            overlay = overlay.getBase() 
        
        return self.__dataSeries.get(overlay)


    def getOverlayPlotColour(self, overlay):
        """Returns an initial colour to use for plots associated with the
        given overlay. If a colour is present in the  :attr:`plotColours`
        dictionary, it is returned. Otherwise a random colour is generated,
        added to ``plotColours``, and returned.
        """
        
        if isinstance(overlay, fsloverlay.ProxyImage):
            overlay = overlay.getBase() 

        colour = self.plotColours.get(overlay)

        if colour is None:
            colour = fslcm.randomDarkColour()
            self.plotColours[overlay] = colour

        return colour


    @actions.action
    def addDataSeries(self):
        """Adds the :class:`.DataSeries` associated with the currently
        selected overlay to the :attr:`PlotPanel.dataSeries` list.
        """
        
        overlay = self._displayCtx.getSelectedOverlay()

        if overlay is None:
            return

        if isinstance(overlay, fsloverlay.ProxyImage):
            overlay = overlay.getBase() 
        
        ds = self.getDataSeries(overlay)

        if ds is None:
            return

        opts = self._displayCtx.getOpts(overlay)

        if isinstance(ds, plotting.FEATTimeSeries):
            toAdd = list(ds.getModelTimeSeries())
        else:
            toAdd = [ds]

        copies = []

        for ds in toAdd:

            # Create the DataSeries copy with
            # the ds.overlay instead of the
            # selected overlay, because if,
            # for example, this is a zstat
            # image in a FEAT directory, these
            # data series will have been
            # created with the corresponding
            # filtered_func_data image, not
            # the zstat image.
            copy = plotting.DataSeries(ds.overlay)

            copy.alpha     = ds.alpha
            copy.lineWidth = ds.lineWidth
            copy.lineStyle = ds.lineStyle
            copy.label     = ds.label

            # Use a new colour for the added
            # DataSeries, because otherwise
            # the added series colour will
            # clash with the overlay colour
            # (see the plotColours class
            # attribute).
            copy.colour = fslcm.randomDarkColour()

            xdata, ydata = self.prepareDataSeries(ds)
            copy.setData(xdata, ydata)

            copies.append(copy)

            # This is disgraceful. It wasn't too bad
            # when this function was defined in the
            # PlotListPanel class, but is a horrendous
            # hack now that it is defined here in the
            # PlotPanel class.
            # 
            # At some stage I will remove this offensive
            # code, and figure out a more robust system
            # for appending this metadata to DataSeries
            # instances. 
            #
            # When the user selects a data series in
            # the list, we want to change the selected
            # overlay/location/volume/etc to the
            # properties associated with the data series.
            # So here we're adding some attributes to
            # each data series instance so that the
            # PlotListPanel.__onListSelect method can
            # update the display properties.
            if isinstance(ds, (plotting.MelodicTimeSeries,
                               plotting.MelodicPowerSpectrumSeries)):
                copy._volume = opts.volume
                
            elif isinstance(ds, (plotting.VoxelTimeSeries,
                                 plotting.VoxelPowerSpectrumSeries)):
                copy._location = opts.getVoxel()
                
        self.dataSeries.extend(copies)
        
        return copies


    @actions.action
    def removeDataSeries(self, *a):
        """Removes the most recently added :class:`.DataSeries` from this
        ``OverlayPlotPanel``.
        """
        if len(self.dataSeries) > 0:
            self.dataSeries.pop()
    

    def createDataSeries(self, overlay):
        """This method must be implemented by sub-classes. It must create and
        return a :class:`.DataSeries` instance for the specified overlay.

        
        .. note:: Sub-class implementations should set the
                  :attr:`.DataSeries.colour` property to that returned by
                  the :meth:`getOverlayPlotColour` method.

        
        Different ``DataSeries`` types need to be re-drawn when different
        properties change. For example, a :class:`.TimeSeries`` instance needs
        to be redrawn when the :attr:`.DisplayContext.location` property
        changes, whereas a :class:`.MelodicTimeSeries` instance needs to be
        redrawn when the :attr:`.VolumeOpts.volume` property changes.

        Therefore, in addition to creating and returning a ``DataSeries``
        instance for the given overlay, sub-class implementations must also
        specify the properties which affect the state of the ``DataSeries``
        instance. These must be specified as two lists:

         - the *targets* list, a list of objects which own the dependant
           properties (e.g. the :class:`.DisplayContext` or
           :class:`.VolumeOpts` instance).

         - The *properties* list, a list of names, each specifying the
           property on the corresponding target.

        This method must therefore return a tuple containing:
        
          - A :class:`.DataSeries` instance, or ``None`` if the overlay
            is incompatible.
          - A list of *target* instances.
          - A list of *property names*.
        
        The target and property name lists must have the same length.
        """
        raise NotImplementedError('createDataSeries must be '
                                  'implemented by sub-classes')

    
    def clearDataSeries(self, overlay):
        """Destroys the internally cached :class:`.DataSeries` for the given
        overlay.
        """

        if isinstance(overlay, fsloverlay.ProxyImage):
            overlay = overlay.getBase()
        
        ds                 = self.__dataSeries  .pop(overlay, None)
        targets, propNames = self.__refreshProps.pop(overlay, ([], []))

        if ds is not None:
            ds.destroy()

        for t, p in zip(targets, propNames):
            try:    t.removeListener(p, self.__name)
            except: pass

        
    def updateDataSeries(self):
        """Makes sure that a :class:`.DataSeries` instance has been created
        for every compatible overlay, and that property listeners are
        correctly registered, so the plot can be refreshed when needed.
        """

        # Make sure that a DataSeries
        # exists for every compatible overlay
        for ovl in self._overlayList:
            if ovl in self.__dataSeries:
                continue

            if isinstance(ovl, fsloverlay.ProxyImage):
                continue

            log.debug('Creating a DataSeries for overlay {}'.format(ovl))

            ds, refreshTargets, refreshProps = self.createDataSeries(ovl)

            if ds is None:
                continue

            self.__dataSeries[  ovl] = ds
            self.__refreshProps[ovl] = (refreshTargets, refreshProps)

        # Make sure that property listeners are
        # registered for every relevant overlay.
        # We only want to listen for properties
        # related to the overlays that are defined
        # by the current value of the showMode
        # property.
        selectedOverlay = self._displayCtx.getSelectedOverlay()
        if   self.showMode == 'all':     targetOverlays = self._overlayList[:]
        elif self.showMode == 'current': targetOverlays = [selectedOverlay]
        else:                            targetOverlays = []

        targetOverlays = [o.getBase() if isinstance(o, fsloverlay.ProxyImage)
                          else o
                          for o in targetOverlays]

        # Build a list of all overlays, ordered by
        # those we are not interested in, followed
        # by those that we are interested in.
        allOverlays = self.__refreshProps.keys()
        allOverlays = set(allOverlays) - set(targetOverlays)
        allOverlays = list(allOverlays) + targetOverlays
        
        # Make sure that property listeners are not
        # registered on overlays that we're not
        # interested in, and are registered on those
        # that we are interested in. The ordering
        # above ensures that we inadvertently don't
        # de-register a listener that we have just
        # registered, from the same target.
        for overlay in allOverlays:

            targets, propNames = self.__refreshProps.get(overlay, (None, None))
            display            = self._displayCtx.getDisplay(overlay)
            addListener        = overlay in targetOverlays

            if addListener:
                if not display.hasListener('enabled', self._name):
                    display.addListener('enabled',
                                        self._name,
                                        self.__displayEnabledChanged)
            else:
                display.removeListener('enabled', self._name)

            if targets is None:
                continue

            ds = self.__dataSeries[overlay]

            if addListener:
                ds.addGlobalListener(self.__name,
                                     self.asyncDraw,
                                     overwrite=True)
            else:
                try:    ds.removeGlobalListener(self.__name)
                except: pass
        
            for target, propName in zip(targets, propNames):
                if addListener:
                    
                    log.debug('Adding listener on {}.{} for {} data '
                              'series'.format(type(target).__name__,
                                              propName,
                                              overlay))
                    
                    target.addListener(propName,
                                       self.__name,
                                       self.asyncDraw,
                                       overwrite=True)
                else:
                    log.debug('Removing listener on {}.{} for {} data '
                              'series'.format(type(target).__name__,
                                              propName,
                                              overlay)) 
                    try:    target.removeListener(propName, self.__name)
                    except: pass


    @actions.toggleControlAction(overlaylistpanel.OverlayListPanel)
    def toggleOverlayList(self):
        """Shows/hides an :class:`.OverlayListPanel`. See
        :meth:`.ViewPanel.togglePanel`.
        """ 
        self.togglePanel(overlaylistpanel.OverlayListPanel,
                         showVis=True,
                         showSave=False,
                         showGroup=False,
                         elistboxStyle=(elistbox.ELB_REVERSE      |
                                        elistbox.ELB_TOOLTIP_DOWN |
                                        elistbox.ELB_NO_ADD       |
                                        elistbox.ELB_NO_REMOVE    |
                                        elistbox.ELB_NO_MOVE),
                         location=wx.LEFT)


    @actions.toggleControlAction(plotlistpanel.PlotListPanel)
    def togglePlotList(self, floatPane=False):
        """Shows/hides a :class:`.PlotListPanel`. See
        :meth:`.ViewPanel.togglePanel`.
        """
        self.togglePanel(plotlistpanel.PlotListPanel,
                         self,
                         location=wx.LEFT,
                         floatPane=floatPane)


    def __showModeChanged(self, *a):
        """Called when the :attr:`showMode` changes.  Makes sure that relevant
        property listeners are registered so the plot can be updated at the
        appropriate time (see the :meth:`updateDataSeries` method).
        """ 
        self.updateDataSeries()
        self.asyncDraw()


    def __dataSeriesChanged(self, *a):
        """Called when the :attr:`dataSeries` list changes. Enables/disables
        the :meth:`removeDataSeries` action accordingly.
        """
        self.removeDataSeries.enabled = len(self.dataSeries) > 0


    def __selectedOverlayChanged(self, *a):
        """Called when the :attr:`.DisplayContext.selectedOverlay` changes.
        Makes sure that relevant property listeners are registered so the
        plot can be updated at the appropriate time (see the
        :meth:`updateDataSeries` method).
        """

        self.updateDataSeries()
        self.asyncDraw()

    
    def __overlayListChanged(self, *a):
        """Called when the :class:`.OverlayList` changes. Makes sure that
        there are no :class:`.DataSeries` instances in the
        :attr:`.PlotPanel.dataSeries` list, or in the internal cache, which
        refer to overlays that no longer exist.

        Also calls :meth:`updateDataSeries`, whic ensures that a
        :class:`.DataSeries` instance for every compatible overlay is cached
        internally.
        """

        for ds in list(self.dataSeries):
            if ds.overlay not in self._overlayList:
                self.dataSeries.remove(ds)
                ds.destroy()

        for overlay in list(self.__dataSeries.keys()):
            if overlay not in self._overlayList:
                self.clearDataSeries(overlay)

        for overlay in self._overlayList:
            display = self._displayCtx.getDisplay(overlay)

            # PlotPanels use the Display.enabled property
            # to toggle on/off overlay plots. We don't want
            # this to interfere with CanvasPanels, which
            # use Display.enabled to toggle on/off overlays.
            display.unsyncFromParent('enabled')

        self.__selectedOverlayChanged()


    def __displayEnabledChanged(self, value, valid, display, name):
        """Called when the :attr:`.Display.enabled` property for any overlay
        changes. Propagates the change on to the corresponding
        :attr:`.DataSeries.enabled` property, and triggers a plot refresh.
        """
        
        ds = self.__dataSeries.get(display.getOverlay())

        if ds is not None:
            ds.enabled = display.enabled
            self.asyncDraw()
