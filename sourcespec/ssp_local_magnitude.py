# -*- coding: utf-8 -*-
"""
Local magnitude calculation for sourcespec.

:copyright:
    2012 Claudio Satriano <satriano@ipgp.fr>

    2013-2014 Claudio Satriano <satriano@ipgp.fr>,
              Emanuela Matrullo <matrullo@geologie.ens.fr>

    2015-2017 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import logging
import numpy as np
from copy import deepcopy
from obspy.signal.filter import envelope
from obspy.signal.invsim import WOODANDERSON
from obspy.signal.util import smooth
from obspy.signal.trigger import trigger_onset
from sourcespec.ssp_util import cosine_taper
from sourcespec.ssp_util import remove_instr_response


def _get_cut_times(config, tr):
    """Get trace cut times between P arrival and end of envelope coda."""
    tr_env = tr.copy()
    # remove the mean...
    tr_env.detrend(type='constant')
    # ...and the linear trend...
    tr_env.detrend(type='linear')
    # ...filter
    freqmin = 1.
    freqmax = 20.
    nyquist = 1./(2. * tr.stats.delta)
    if freqmax >= nyquist:
        freqmax = nyquist * 0.999
        msg = '%s: maximum frequency for bandpass filtering ' % tr.id
        msg += 'in local magnitude computation is larger than or equal '
        msg += 'to Nyquist. Setting it to %s Hz' % freqmax
        logging.warning(msg)
    tr_env.filter(type='bandpass', freqmin=freqmin, freqmax=freqmax)
    tr_env.data = envelope(tr_env.data)
    tr_env.data = smooth(tr_env.data, 100)

    # Skip traces which do not have arrivals
    try:
        p_arrival_time = tr.stats.arrivals['P'][1]
    except Exception:
        logging.warning('%s: Trace has no P arrival: skipping trace' % tr.id)
        raise RuntimeError
    t1 = p_arrival_time - config.pre_mag_time
    t2 = p_arrival_time + config.pre_mag_time

    tr_noise = tr_env.copy()
    tr_signal = tr_env.copy()
    tr_noise.trim(starttime=t1, endtime=p_arrival_time,
                  pad=True, fill_value=0)
    tr_signal.trim(starttime=p_arrival_time, endtime=t2,
                   pad=True, fill_value=0)
    ampmin = tr_noise.data.mean()
    ampmax = tr_signal.data.mean()
    if ampmax <= ampmin:
        logging.warning(
            '%s: Trace has too high noise before P arrival: '
            'skipping trace' % tr.id)
        raise RuntimeError

    trigger = trigger_onset(tr_env.data, ampmax, ampmin,
                            max_len=9e99, max_len_delete=False)[0]
    t0 = p_arrival_time
    t1 = t0 + trigger[-1] * tr.stats.delta
    # import matplotlib.pyplot as plt
    # fig, ax = plt.subplots(2, 1, sharex=True)
    # fig.suptitle(tr.id)
    # ax[0].plot(tr.times(), tr, color='k')
    # ax[0].grid(True)
    # ax[1].plot(tr_env.times(), tr_env, color='k')
    # ax[1].axvline(t0 - tr.stats.starttime, color='k', linestyle='--')
    # ax[1].axvline(t1 - tr.stats.starttime, color='k', linestyle='--')
    # ax[1].grid(True)
    # ax[1].set_xlabel('Time (s)')
    # plt.show()
    return t0, t1


def _process_trace(config, tr, t0, t1):
    """Convert to Wood-Anderson, filter, trim."""
    tr_process = tr.copy()
    # Do a preliminary trim, in order to check if there is enough
    # data within the selected time window
    tr_process.trim(starttime=t0, endtime=t1, pad=True, fill_value=0)
    npts = len(tr_process.data)
    if npts == 0:
        logging.warning('%s: No data for the selected cut interval: '
                        'skipping trace' % tr.id)
        raise RuntimeError
    nzeros = len(np.where(tr_process.data == 0)[0])
    if nzeros > npts/4:
        logging.warning('%s: Too many gaps for the selected cut '
                        'interval: skipping trace' % tr.id)
        raise RuntimeError

    # If the check is ok, recover the full trace
    # (it will be cutted later on)
    tr_process = tr.copy()
    # remove the mean...
    tr_process.detrend(type='constant')
    # ...and the linear trend...
    tr_process.detrend(type='linear')
    # ...filter
    # TODO: parametrize?
    tr_process.filter(type='bandpass', freqmin=0.1, freqmax=20)
    # remove response and convert to Wood-Anderson
    remove_instr_response(
        tr_process, config.correct_instrumental_response, config.pre_filt)
    # note: conversion to Wood-Anderson integrates the signal once
    if tr.stats.instrtype == 'acc':
        WA_double_int = deepcopy(WOODANDERSON)
        # we remove a zero to add an integration step
        WA_double_int['zeros'].pop()
        tr_process.simulate(paz_simulate=WA_double_int)
    else:
        tr_process.simulate(paz_simulate=WOODANDERSON)
    # trim...
    tr_process.trim(starttime=t0, endtime=t1, pad=True, fill_value=0)
    # ...and taper
    cosine_taper(tr_process.data, width=config.taper_halfwidth)
    return tr_process


def local_magnitude(config, st, proc_st, sourcepar, sourcepar_err):
    """Compute local magnitude from min/max amplitude."""
    # We only use traces selected for proc_st
    trace_ids = set(tr.id for tr in proc_st)
    for tr_id in sorted(trace_ids):
        tr = st.select(id=tr_id)[0]

        # only analyze traces for which we have the other
        # source paramters defined
        key = '%sH %s' % (tr_id[:-1], tr.stats.instrtype)
        try:
            par = sourcepar[key]
        except KeyError:
            continue

        comp = tr.stats.channel
        if comp[-1] in ['Z', 'H']:
            continue

        try:
            t0, t1 = _get_cut_times(config, tr)
            tr_process = _process_trace(config, tr, t0, t1)
        except RuntimeError:
            continue

        # a_max must be in millimiters for local magnitude computation
        a_max = np.abs(tr_process.max())*1000.
        h_dist = tr_process.stats.hypo_dist

        # Local magnitude
        ml = np.log10(a_max) + np.log10(h_dist / 100.0) + \
            0.00301 * (h_dist - 100.0) + 3.0

        statId = '%s %s' % (tr_id, tr.stats.instrtype)
        logging.info('%s: Ml %.1f' % (statId,  ml))
        try:
            old_ml = par['Ml']
            ml = 0.5 * (ml + old_ml)
        except KeyError:
            pass
        par['Ml'] = ml

    # average local magnitude
    # build ml_values: use np.nan for missing values
    ml_values = np.array([x.get('Ml', np.nan) for x in sourcepar.values()])
    ml_values = ml_values[~np.isnan(ml_values)]
    Ml = np.mean(ml_values)
    logging.info('Network Local Magnitude: %.2f' % Ml)
