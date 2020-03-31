# -*- coding: utf-8 -*-
"""
Trace plotting routine.

:copyright:
    2015-2019 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import math
import logging
from sourcespec.ssp_version import get_git_version
logger = logging.getLogger(__name__.split('.')[-1])


phase_label_pos = {'P': 0.9, 'S': 0.93}
phase_label_color = {'P': 'black', 'S': 'black'}


def _import_mpl(config):
    import matplotlib
    matplotlib.rcParams['pdf.fonttype'] = 42  # to edit text in Illustrator
    # Reduce logging level for Matplotlib to avoid DEBUG messages
    mpl_logger = logging.getLogger('matplotlib')
    mpl_logger.setLevel(logging.WARNING)
    global plt
    import matplotlib.pyplot as plt
    if not config.PLOT_SHOW:
        plt.switch_backend('Agg')
    global PdfPages
    from matplotlib.backends.backend_pdf import PdfPages
    global transforms
    global patches
    global PathEffects
    import matplotlib.transforms as transforms
    import matplotlib.patches as patches
    import matplotlib.patheffects as PathEffects
    from matplotlib.ticker import ScalarFormatter as sf
    global ScalarFormatter
    class ScalarFormatter(sf):  #NOQA
        def _set_format(self, vmin=None, vmax=None):
            self.format = '%1.1f'


def _nplots(st, maxlines, ncols):
    # Determine the number of plots:
    nplots = 0
    for station in set(x.stats.station for x in st.traces):
        st_sel = st.select(station=station)
        # 'code' is band+instrument code
        for code in set(x.stats.channel[0:2] for x in st_sel):
            nplots += 1
    nlines = int(math.ceil(nplots/ncols))
    if nlines > maxlines:
        nlines = maxlines
    if nplots < ncols:
        ncols = 1
    return nlines, ncols


def _make_fig(config, nlines, ncols):
    if nlines <= 3:
        figsize = (16, 9)
    else:
        figsize = (16, 18)
    fig = plt.figure(figsize=figsize)
    # Create an invisible axis and use it for title and footer
    ax0 = fig.add_subplot(111, label='ax0')
    ax0.set_axis_off()
    # Add event information as a title
    hypo = config.hypo
    textstr = 'evid: {} lon: {:.3f} lat: {:.3f} depth: {:.1f} km ' +\
              'time: {}'
    textstr = textstr.format(
        hypo.evid, hypo.longitude, hypo.latitude, hypo.depth,
        hypo.origin_time.format_iris_web_service())
    ax0.text(0., 1.06, textstr, fontsize=12,
             ha='left', va='top', transform=ax0.transAxes)
    if config.options.evname is not None:
        textstr = config.options.evname
        ax0.text(0., 1.1, textstr, fontsize=14,
                 ha='left', va='top', transform=ax0.transAxes)
    # Add code information at the figure bottom
    textstr = 'SourceSpec v{} '.format(get_git_version())
    ax0.text(1., -0.1, textstr, fontsize=10,
             ha='right', va='top', transform=ax0.transAxes)
    axes = []
    for n in range(nlines*ncols):
        plotn = n+1
        if plotn == 1:
            ax = fig.add_subplot(nlines, ncols, plotn)
        else:
            ax = fig.add_subplot(nlines, ncols, plotn, sharex=axes[0])
        ax.grid(True, which='both', linestyle='solid', color='#DDDDDD',
                zorder=0)
        ax.set_axisbelow(True)
        ax.xaxis.set_tick_params(which='both', labelbottom=False)
        ax.yaxis.set_tick_params(which='both', labelleft=True)
        ax.tick_params(width=2)  # FIXME: ticks are below grid lines!
        ax.tick_params(labelsize=8)
        ax.yaxis.offsetText.set_fontsize(8)
        yfmt = ScalarFormatter()
        yfmt.set_powerlimits((-1, 1))
        ax.yaxis.set_major_formatter(yfmt)
        axes.append(ax)
    fig.subplots_adjust(hspace=.1, wspace=.20)
    return fig, axes


def _savefig(config, figures, async_plotter):
    evid = config.hypo.evid
    figfile_base = os.path.join(config.options.outdir, evid + '.traces.')
    fmt = config.PLOT_SAVE_FORMAT
    if fmt == 'pdf_multipage':
        figfile = figfile_base + 'pdf'
        with PdfPages(figfile) as pdf:
            for fig in figures:
                pdf.savefig(fig)
            if not config.PLOT_SHOW:
                fig.clf()
        logger.info('Trace plots saved to: ' + figfile)
        return
    for n, fig in enumerate(figures):
        if len(figures) == 1:
            figfile = figfile_base + fmt
        else:
            figfile = figfile_base + '{:02d}.{}'.format(n, fmt)
        if config.PLOT_SHOW or (async_plotter is None):
            fig.savefig(figfile, bbox_inches='tight')
        else:
            async_plotter.save(fig.canvas, figfile, bbox_inches='tight')
        logger.info('Trace plots saved to: ' + figfile)
        if not config.PLOT_SHOW:
            fig.clf()


def _plot_trace(config, trace, ntraces, tmax,
                spec_st, ax, ax_text, trans, trans3, path_effects):
    t1 = (trace.stats.arrivals['P'][1] - config.pre_p_time)
    t2 = (trace.stats.arrivals['S'][1] + 3 * config.s_win_length)
    trace.trim(starttime=t1, endtime=t2, pad=True, fill_value=0)
    orientation = trace.stats.channel[-1]
    if orientation in config.vertical_channel_codes:
        color = 'purple'
    if orientation in config.horizontal_channel_codes_1:
        color = 'green'
        if ntraces > 1:
            trace.data = (trace.data / tmax - 1) * tmax
    if orientation in config.horizontal_channel_codes_2:
        color = 'blue'
        if ntraces > 1:
            trace.data = (trace.data / tmax + 1) * tmax
    alpha = 1.0
    # if spec_st is given, grey out traces that have no spectrum
    # (i.e., low spectral S/N)
    if spec_st:
        if not spec_st.select(id=trace.get_id()):
            alpha = 0.3
    ax.plot(trace.times(), trace, color=color,
            alpha=alpha, zorder=20, rasterized=True)
    ax.text(0.05, trace.data.mean(), trace.stats.channel,
            fontsize=8, color=color, transform=trans3, zorder=22,
            path_effects=path_effects)
    for phase in 'P', 'S':
        a = trace.stats.arrivals[phase][1] - trace.stats.starttime
        text = trace.stats.arrivals[phase][0]
        ax.axvline(a, linestyle='--',
                   color=phase_label_color[phase], zorder=21)
        ax.text(a, phase_label_pos[phase], text,
                fontsize=8, transform=trans,
                zorder=22, path_effects=path_effects)
    # Noise window
    try:
        N1 = trace.stats.arrivals['N1'][1] - trace.stats.starttime
        N2 = trace.stats.arrivals['N2'][1] - trace.stats.starttime
        rect = patches.Rectangle((N1, 0), width=N2-N1, height=1,
                                 transform=trans, color='#eeeeee',
                                 alpha=0.5, zorder=-1)
        ax.add_patch(rect)
    except KeyError:
        pass
    # S-wave window
    S1 = trace.stats.arrivals['S1'][1] - trace.stats.starttime
    S2 = trace.stats.arrivals['S2'][1] - trace.stats.starttime
    rect = patches.Rectangle((S1, 0), width=S2-S1, height=1,
                             transform=trans, color='yellow',
                             alpha=0.5, zorder=-1)
    ax.add_patch(rect)
    if not ax_text:
        text_y = 0.1
        color = 'black'
        ax_text = '%s %s %.1f km (%.1f km)' %\
                  (trace.id[0:-4],
                   trace.stats.instrtype,
                   trace.stats.hypo_dist,
                   trace.stats.epi_dist)
        ax.text(0.05, text_y, ax_text,
                fontsize=8,
                horizontalalignment='left',
                verticalalignment='bottom',
                color=color,
                transform=ax.transAxes,
                zorder=50,
                path_effects=path_effects)
        ax_text = True


def _add_labels(axes, plotn, ncols):
    # Show the x-labels only for "ncols" plots before "plotn"
    for ax in axes[plotn-ncols:plotn]:
        ax.xaxis.set_tick_params(which='both', labelbottom=True)
        ax.set_xlabel('Time (s)', fontsize=8)


def plot_traces(config, st, spec_st=None, ncols=4, block=True,
                async_plotter=None):
    """
    Plot displacement traces.

    Display to screen and/or save to file.
    """
    # Check config, if we need to plot at all
    if not config.PLOT_SHOW and not config.PLOT_SAVE:
        return
    _import_mpl(config)

    nlines, ncols = _nplots(st, config.plot_traces_maxrows, ncols)
    figures = []
    fig, axes = _make_fig(config, nlines, ncols)
    figures.append(fig)

    # Path effect to contour text in white
    path_effects = [PathEffects.withStroke(linewidth=3, foreground="white")]

    # Plot!
    plotn = 0
    stalist = sorted(set(
        (t.stats.hypo_dist, t.stats.station, t.stats.channel[0:2])
        for t in st))
    for t in stalist:
        plotn += 1
        # 'code' is band+instrument code
        _, station, code = t
        st_sel = st.select(station=station)
        if plotn > nlines*ncols:
            _add_labels(axes, plotn-1, ncols)
            fig, axes = _make_fig(config, nlines, ncols)
            figures.append(fig)
            plotn = 1
        ax_text = False
        ax = axes[plotn-1]
        instrtype = [t.stats.instrtype for t in st_sel.traces
                     if t.stats.channel[0:2] == code][0]
        if instrtype == 'acc':
            ax.set_ylabel(u'Acceleration (m/s²)', fontsize=8, labelpad=0)
        elif instrtype == 'shortp' or instrtype == 'broadb':
            ax.set_ylabel('Velocity (m/s)', fontsize=8, labelpad=0)
        # Custom transformation for plotting phase labels:
        # x coords are data, y coords are axes
        trans = transforms.blended_transform_factory(ax.transData,
                                                     ax.transAxes)
        trans2 = transforms.blended_transform_factory(ax.transAxes,
                                                      ax.transData)
        trans3 = transforms.offset_copy(trans2, fig=fig, x=0, y=0.1)

        maxes = [abs(t.max()) for t in st_sel.traces
                 if t.stats.channel[0:2] == code]
        ntraces = len(maxes)
        tmax = max(maxes)
        for trace in st_sel.traces:
            if trace.stats.channel[0:2] != code:
                continue
            _plot_trace(config, trace, ntraces, tmax,
                        spec_st, ax, ax_text, trans, trans3, path_effects)

    # Add lables for the last figure
    _add_labels(axes, plotn, ncols)
    # Turn off the unused axes
    for ax in axes[plotn:]:
        ax.set_axis_off()

    if config.PLOT_SHOW:
        plt.show(block=block)
    if config.PLOT_SAVE:
        _savefig(config, figures, async_plotter)
