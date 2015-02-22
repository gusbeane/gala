# coding: utf-8

""" Port of NAFF to Python """

from __future__ import division, print_function

__author__ = "adrn <adrn@astro.columbia.edu>"

# Standard library
import time

# Third-party
from astropy import log as logger
import numpy as np
from numpy.fft import fftfreq
try:
    from pyfftw.interfaces.numpy_fft import fft
except ImportError:
    from numpy.fft import fft

import scipy.optimize as so
from scipy.integrate import simps

# Project
from .core import classify_orbit, align_circulation_with_z

__all__ = ['NAFF', 'poincare_polar', 'orbit_to_freqs']

def hanning(x):
    return 1 + np.cos(x)

def poincare_polar(w):
    ndim = w.shape[-1]//2

    R = np.sqrt(w[...,0]**2 + w[...,1]**2)
    # phi = np.arctan2(w[...,1], w[...,0])
    phi = np.arctan2(w[...,0], w[...,1])

    vR = (w[...,0]*w[...,0+ndim] + w[...,1]*w[...,1+ndim]) / R
    vPhi = w[...,0]*w[...,1+ndim] - w[...,1]*w[...,0+ndim]

    fs = []
    fs.append(R + 1j*vR)
    fs.append(np.sqrt(2*np.abs(vPhi))*(np.cos(phi) + 1j*np.sin(phi)))  # PP
    fs.append(w[...,2] + 1j*w[...,2+ndim])

    return fs

class NAFF(object):

    def __init__(self, t):
        """ Implementation of the Numerical Analysis of Fundamental Frequencies (NAFF)
            method of Laskar, later modified by Valluri and Merritt (see references below).

            This algorithm attempts to numerically find the fundamental frequencies of an
            input orbit (time series) and can also find approximate actions for the orbit.
            The basic idea is to Fourier transform the orbit convolved with a Hanning filter,
            find the most significant peak, subtract that frequency, and iterate on this
            until convergence or for a fixed number of terms. The fundamental frequencies
            can then be solved for by assuming that the frequencies found by the above method
            are integer combinations of the fundamental frequencies.

            For more information, see:

                - Laskar, J., Froeschlé, C., and Celletti, A. (1992)
                - Laskar, J. (1993)
                - Papaphilippou, Y. and Laskar, J. (1996)
                - Valluri, M. and Merritt, D. (1998)

            Parameters
            ----------
            t : array_like
                Array of times.
        """

        self.t = t
        self.ts = 0.5*(t[-1] + t[0])
        self.T = 0.5*(t[-1] - t[0])
        self.tz = t - self.ts

        # pre-compute values of Hanning filter
        self.chi = hanning(self.tz*np.pi/self.T)

    def frequency(self, f):
        """ Find the most significant frequency of a (complex) time series, :math:`f(t)`,
            by Fourier transforming the function convolved with a Hanning filter and
            picking the biggest peak. This assumes `f` is aligned with / given at the
            times specified when constructing this object.

            Parameters
            ----------
            f : array_like
                Complex time-series, :math:`q(t) + i p(t)`.
        """

        # number of data points or time samples
        ndata = len(f)

        # take Fourier transform of input (complex) function f
        logger.log(0, "Fourier transforming...")
        t1 = time.time()
        fff = fft(f) / np.sqrt(ndata)
        omegas = 2*np.pi*fftfreq(f.size, self.t[1]-self.t[0])
        logger.log(0, "...done. Took {} seconds to FFT.".format(time.time()-t1))

        # # plot the FFT
        # import matplotlib.pyplot as plt
        # plt.figure(figsize=(12,8))
        # plt.semilogx(omegas, fff.real, marker=None)
        # plt.xlim(1E-3, 1E-1)
        # plt.show()
        # sys.exit(0)

        A = 1./np.sqrt(ndata - 1.)
        xf = A * fff.real * (-1)**np.arange(ndata)
        yf = A * fff.imag * (-1)**np.arange(ndata)

        # find max of xf, yf, get index of row -- this is just an initial guess
        xyf = np.vstack((xf,yf))
        xyf_abs = np.abs(xyf)
        wmax = np.max(xyf_abs, axis=0).argmax()
        if xf[wmax] != 0.:
            signx = np.sign(xf[wmax])
            signy = np.sign(yf[wmax])
        else:
            # return early -- "this may be an axial or planar orbit"
            return 0.

        # find the frequency associated with this index
        omega0 = omegas[wmax]
        signo = np.sign(omega0)

        # now that we have a guess for the maximum, convolve with Hanning filter and re-solve
        xf = f.real
        yf = f.imag

        # window around estimated best frequency
        omin = omega0 - np.pi/self.T
        omax = omega0 + np.pi/self.T

        def transform(x):
            return (x - omin) / (omax - omin)

        def invtransform(y):
            return y*(omax - omin) + omin

        def phi_w(w):
            """ This function numerically computes phi(ω), as in
                Eq. 12 in Valluri & Merritt (1998).
            """
            w = invtransform(w)
            # real part of integrand of Eq. 12
            zreal = self.chi * (xf*np.cos(w*self.tz) + yf*np.sin(w*self.tz))
            ans = simps(zreal, x=self.tz)
            # return -(ans*signx*signo)/(2.*self.T)
            return -np.abs(ans/(2.*self.T))

        w = np.linspace(0, 1, 50)
        phi_vals = np.array([phi_w(ww) for ww in w])
        phi_ix = phi_vals.argmin()

        if np.all(np.abs(phi_vals) < 1E-10):
            init_w = 0.5
        else:
            init_w = w[phi_ix]

        res = so.fmin_slsqp(phi_w, x0=init_w, acc=1E-9,
                            bounds=[(0,1)], disp=0, iter=50,
                            full_output=True)
        freq,fx,its,imode,smode = res
        freq = invtransform(freq)

        # -------------------------------------------------------------
        # import uuid
        # import matplotlib.pyplot as plt
        # plt.figure(figsize=(12,8))
        # w = np.linspace(0, 1, 100)
        # plt.plot(invtransform(w), np.array([phi_w(ww) for ww in w]))
        # plt.axvline(freq)
        # plt.axvline(invtransform(init_w), linestyle='dashed')
        # plt.title(str(imode))
        # plt.savefig("/Users/adrian/Downloads/{}.png".format(uuid.uuid4()))
        # plt.show()
        # sys.exit(0)
        # -------------------------------------------------------------

        # failed by starting at minimum, try instead starting from middle
        if imode != 0:
            init_w = 0.5
            res = so.fmin_slsqp(phi_w, x0=init_w, acc=1E-9,
                                bounds=[(0,1)], disp=0, iter=100,
                                full_output=True)
            freq,fx,its,imode,smode = res
            freq = invtransform(freq)

        if imode != 0:
            # TEST
            # import matplotlib.pyplot as plt
            # plt.figure(figsize=(12,8))
            # w = np.linspace(0, 1, 100)
            # plt.plot(invtransform(w), np.array([phi_w(ww) for ww in w]))
            # plt.axvline(freq)
            # plt.axvline(invtransform(init_w), linestyle='dashed')
            # plt.title(str(imode))
            # plt.show()
            # sys.exit(0)
            # TEST

            raise ValueError("Function minimization to find best frequency failed with:\n"
                             "\t {} : {}".format(imode, smode))

        return freq[0]

    def frecoder(self, f, nintvec=12, break_condition=1E-7):
        """ For a given number of iterations, or until the break condition is met,
            solve for strongest frequency of the input time series, then subtract
            it from the time series.

            This function is meant to be the same as the subroutine FRECODER in
            Monica Valluri's Fortran NAFF routines.

            Parameters
            ----------
            f : array_like
                Complex time-series, :math:`q(t) + i p(t)`.
            nintvec : int
                Number of integer vectors to find or number of frequencies to find and subtract.
            break_condition : numeric
                Break the iterations of the time series maximum value or amplitude of the
                subtracted frequency is smaller than this value. Set to 0 if you want to always
                iterate for `nintvec` frequencies.
        """

        # initialize container arrays
        ecap = np.zeros((nintvec,len(self.t)), dtype=np.complex64)
        nu = np.zeros(nintvec)
        A = np.zeros(nintvec)
        phi = np.zeros(nintvec)

        fk = f.copy()
        logger.debug("-"*50)
        logger.debug("k    ωk    Ak    φk(deg)    ak")
        for k in range(nintvec):
            nu[k] = self.frequency(fk)

            if k == 0:
                # compute exp(iωt) for first frequency
                ecap[k] = np.exp(1j*nu[k]*self.t)
            else:
                ecap[k] = self.gso(ecap, nu[k], k)

            # get complex amplitude by projecting exp(iωt) on to f(t)
            ab = self.hanning_product(fk, ecap[k])
            A[k] = np.abs(ab)
            phi[k] = np.arctan2(ab.imag, ab.real)

            # print(nu[k], ab, A[k], phi[k])
            # if k == 1:
            #     sys.exit(0)

            # new fk has the previous frequency subtracted out
            fk,fmax = self.sub_chi(fk, ecap[k], ab)

            logger.debug("{}  {:.6f}  {:.6f}  {:.2f}  {:.6f}"
                         .format(k,nu[k],A[k],np.degrees(phi[k]),ab))

            if break_condition is not None and (fmax < break_condition or A[k] < break_condition):
                break

        return -nu[:k+1], A[:k+1], phi[:k+1]

    def hanning_product(self, u1, u2):
        r""" Compute the scalar product of two 'vectors', `u1` and `u2`.
            The scalar product is defined with the Hanning filter as

            .. math::

                <u_1, u_2> = \frac{1}{2 T} \int \, u_1(t) \, \chi(t) \, u_2^*(t)\,dt

            Parameters
            ----------
            u1 : array_like
            u2 : array_like
        """

        # First find complex conjugate of vector u2 and construct integrand
        integ = u1 * np.conj(u2) * self.chi
        integ_r = integ.real
        integ_i = integ.imag

        # Integrate the real part
        real = simps(integ_r, x=self.tz) / (2.*self.T)

        # Integrate Imaginary part
        imag = simps(integ_i, x=self.tz) / (2.*self.T)

        return real + imag*1j

    def gso(self, ecap, nu, k):
        r""" Gram-Schmidt orthonormalization of the function
        ..math::

            e_k(t) = \exp (i \omega_k t)

        with all previous functions.

        Parameters
        ----------
        ecap : array_like
        nu : numeric
        k : int
            Index of maximum freq. found so far.
        """

        # coefficients
        c_ik = np.zeros(k, dtype=np.complex64)

        u_n = np.exp(1j*nu*self.t)

        # first find the k complex constants cik(k,ndata):
        for j in range(k):
            c_ik[j] = self.hanning_product(u_n, ecap[j])

        # Now construct the orthogonal vector
        e_i = u_n - np.sum(c_ik[:,np.newaxis]*ecap[:k], axis=0)

        # Now normalize this vector
        prod = self.hanning_product(e_i, e_i)

        norm = 1. / np.sqrt(prod)
        if prod == 0.:
            norm = 0. + 0j

        return e_i*norm

    def sub_chi(self, f_km1, ecap_k, a_k):
        # remove the new orthogonal frequency component from the f_k
        f_k = f_km1 - a_k*ecap_k

        # now compute the largest amplitude of the residual function f_k
        fmax = np.max(np.abs(f_k))

        return f_k, fmax

    def find_fundamental_frequencies(self, fs, nintvec=15, imax=15, break_condition=1E-7):
        """ Solve for the fundamental frequencies of the given time series, `fs`

            TODO:
        """

        # containers
        freqs = []
        As = []
        amps = []
        phis = []
        nqs = []

        ntot = 0
        ndim = len(fs)

        for i in range(ndim):
            nu,A,phi = self.frecoder(fs[i], nintvec=nintvec, break_condition=break_condition)
            freqs.append(-nu)
            As.append(A*np.exp(1j*phi))
            amps.append(A)
            phis.append(phi)
            nqs.append(np.zeros_like(nu) + i)
            ntot += len(nu)

        d = np.zeros(ntot, dtype=zip(('freq','A','|A|','phi','n'),
                                     ('f8','c8','f8','f8',np.int)))
        d['freq'] = np.concatenate(freqs)
        d['A'] = np.concatenate(As)
        d['|A|'] = np.concatenate(amps)
        d['phi'] = np.concatenate(phis)
        d['n'] = np.concatenate(nqs).astype(int)

        # sort terms by amplitude
        d = d[d['|A|'].argsort()[::-1]]

        # assume largest amplitude is the first fundamental frequency
        ffreq = np.zeros(ndim)
        ffreq_ixes = np.zeros(ndim, dtype=int)
        nqs = np.zeros(ndim, dtype=int)

        # first frequency is largest amplitude, nonzero freq.
        ixes = np.where(np.abs(d['freq']) > 1E-5)[0]
        ffreq[0] = d[ixes[0]]['freq']
        ffreq_ixes[0] = ixes[0]
        nqs[0] = d[ixes[0]]['n']

        if ndim == 1:
            return ffreq, d, ffreq_ixes

        # choose the next nontrivially related frequency as the 2nd fundamental:
        #   TODO: why 1E-6? this isn't well described in the papers...
        ixes = np.where((np.abs(d['freq']) > 1E-5) &
                        (d['n'] != d[ffreq_ixes[0]]['n']) &
                        (np.abs(np.abs(ffreq[0]) - np.abs(d['freq'])) > 1E-6))[0]
        ffreq[1] = d[ixes[0]]['freq']
        ffreq_ixes[1] = ixes[0]
        nqs[1] = d[ixes[0]]['n']

        if ndim == 2:
            return ffreq[nqs.argsort()], d, ffreq_ixes[nqs.argsort()]

        # # -------------
        # # brute-force method for finding third frequency: find maximum error in (n*f1 + m*f2 - f3)

        # # first define meshgrid of integer vectors
        # nvecs = np.vstack(np.vstack(np.mgrid[-imax:imax+1,-imax:imax+1].T))
        # err = np.zeros(ntot)
        # for i in range(ffreq_ixes[1]+1, ntot):
        #     # find best solution for each integer vector
        #     err[i] = np.abs(d[i]['freq'] - nvecs.dot(ffreq[:2])).min()

        #     if err[i] > 1E-6:
        #         break

        #     i = np.nan

        # if np.isnan(i):
        #     raise ValueError("Failed to find third fundamental frequency.")

        # ffreq[2] = d[i]['freq']
        # ffreq_ixes[2] = i

        # for now, third frequency is just largest amplitude frequency in the remaining dimension
        #   TODO: why 1E-6? this isn't well described in the papers...
        ixes = np.where((np.abs(d['freq']) > 1E-5) &
                        (d['n'] != d[ffreq_ixes[0]]['n']) &
                        (d['n'] != d[ffreq_ixes[1]]['n']) &
                        (np.abs(np.abs(ffreq[0]) - np.abs(d['freq'])) > 1E-6) &
                        (np.abs(np.abs(ffreq[1]) - np.abs(d['freq'])) > 1E-6))[0]

        ffreq[2] = d[ixes[0]]['freq']
        ffreq_ixes[2] = ixes[0]
        nqs[2] = d[ixes[0]]['n']

        if not np.all(np.unique(sorted(nqs)) == [0,1,2]):
            raise ValueError("Don't have x,y,z frequencies.")

        return ffreq[nqs.argsort()], d, ffreq_ixes[nqs.argsort()]

    def find_integer_vectors(self, ffreqs, d, imax=15):
        """ TODO """

        ntot = len(d)

        # define meshgrid of integer vectors
        nfreqs = len(ffreqs)
        slc = [slice(-imax,imax+1,None)]*nfreqs
        nvecs = np.vstack(np.vstack(np.mgrid[slc].T))

        # integer vectors
        d_nvec = np.zeros((ntot,nfreqs))
        err = np.zeros(ntot)
        for i in range(ntot):
            this_err = np.abs(d[i]['freq'] - nvecs.dot(ffreqs))
            err[i] = this_err.min()
            d_nvec[i] = nvecs[this_err.argmin()]

        return d_nvec

    def find_actions(self):
        """ Reconstruct approximations to the actions using Percivals equation """
        pass

def orbit_to_freqs(t, w, force_box=False, silently_fail=True, **kwargs):
    """
    Compute the fundamental frequencies of an orbit, ``w``. If not forced, this
    function tries to figure out whether the input orbit is a tube or box orbit and
    then uses the appropriate set of coordinates (Poincaré polar coordinates for tube,
    ordinary Cartesian for box). Any extra keyword arguments (``kwargs``) are passed
    to `NAFF.find_fundamental_frequencies`.

    Parameters
    ----------
    t : array_like
        Array of times.
    w : array_like
        The orbit to analyze. Should have shape (len(t),6).
    force_box : bool (optional)
        Force the routine to assume the orbit is a box orbit. Default is ``False``.
    silently_fail : bool (optional)
        Return NaN's and None's if NAFF fails, rather than raising an exception.
    **kwargs
        Any extra keyword arguments are passed to `NAFF.find_fundamental_frequencies`.

    """

    if w.ndim == 3:
        # remove extra length-1 dimension (assumed to be axis=1)
        w = w[:,0]

    # now get other frequencies
    if force_box:
        is_tube = False
    else:
        circ = classify_orbit(w)
        is_tube = np.any(circ)

    naff = NAFF(t)

    d = None
    ixes = None
    if is_tube:
        # need to flip coordinates until circulation is around z axis
        new_ws = align_circulation_with_z(w, circ)

        fs = poincare_polar(new_ws)
        if silently_fail:
            try:
                logger.info('Solving for Rφz frequencies...')
                fRphiz,d,ixes = naff.find_fundamental_frequencies(fs, **kwargs)
            except:
                fRphiz = np.ones(3)*np.nan
        else:
            logger.info('Solving for Rφz frequencies...')
            fRphiz,d,ixes = naff.find_fundamental_frequencies(fs, **kwargs)

        freqs = fRphiz

    else:
        # first get x,y,z frequencies
        logger.info('Solving for XYZ frequencies...')
        fs = [(w[:,j] + 1j*w[:,j+3]) for j in range(3)]

        if silently_fail:
            try:
                fxyz,d,ixes = naff.find_fundamental_frequencies(fs, **kwargs)
            except:
                fxyz = np.ones(3)*np.nan
        else:
            fxyz,d,ixes = naff.find_fundamental_frequencies(fs, **kwargs)

        freqs = fxyz

    return freqs, d, ixes, is_tube