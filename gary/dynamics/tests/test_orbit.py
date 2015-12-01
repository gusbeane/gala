# coding: utf-8

""" Test ...  """

from __future__ import division, print_function

__author__ = "adrn <adrn@astro.columbia.edu>"

# Third-party
from astropy.coordinates import SphericalRepresentation, Galactic
import astropy.units as u
import numpy as np
import pytest

# Project
from ..orbit import *
from ...potential import HernquistPotential, LogarithmicPotential
from ...units import galactic, solarsystem

def make_known_orbit(tmpdir, x, vx, potential, name):
    # See Binney & Tremaine (2008) Figure 3.8 and 3.9
    E = -0.337
    y = 0.
    vy = np.sqrt(2*(E - potential.value([x,y,0.])))[0]

    w = [x,y,0.,vx,vy,0.]
    t,ws = potential.integrate_orbit(w, dt=0.05, nsteps=10000)

    # fig,ax = pl.subplots(1,1)
    # ax.plot(ws[0], ws[1])
    # fig = plot_orbits(ws, linestyle='none', alpha=0.1)
    # fig.savefig(os.path.join(str(tmpdir), "{}.png".format(name)))
    # logger.debug(os.path.join(str(tmpdir), "{}.png".format(name)))

    return CartesianOrbit.from_w(ws, units=galactic)

def test_circulation(tmpdir):

    potential = LogarithmicPotential(v_c=1., r_h=0.14, q1=1., q2=0.9, q3=1.,
                                     units=galactic)

    # individual
    w1 = make_known_orbit(tmpdir, 0.5, 0., potential, "loop")
    circ = w1.circulation()
    assert circ.shape == (3,)
    assert circ.sum() == 1

    w2 = make_known_orbit(tmpdir, 0., 1.5, potential, "box")
    circ = w2.circulation()
    assert circ.shape == (3,)
    assert circ.sum() == 0

    # try also for both, together
    w3 = combine(w1,w2)
    circ = w3.circulation()
    assert circ.shape == (3,2)
    assert np.allclose(circ.sum(axis=0), [1,0])

def test_align_circulation():

    t = np.linspace(0,100,1024)
    w = np.zeros((6,1024,4))

    # loop around x axis
    w[1,:,0] = np.cos(t)
    w[2,:,0] = np.sin(t)
    w[4,:,0] = -np.sin(t)
    w[5,:,0] = np.cos(t)

    # loop around y axis
    w[0,:,1] = -np.cos(t)
    w[2,:,1] = np.sin(t)
    w[3,:,1] = np.sin(t)
    w[5,:,1] = np.cos(t)

    # loop around z axis
    w[0,:,2] = np.cos(t)
    w[1,:,2] = np.sin(t)
    w[3,:,2] = -np.sin(t)
    w[4,:,2] = np.cos(t)

    # box
    w[0,:,3] = np.cos(t)
    w[1,:,3] = -np.cos(0.5*t)
    w[2,:,3] = np.cos(0.25*t)
    w[3,:,3] = -np.sin(t)
    w[4,:,3] = 0.5*np.sin(0.5*t)
    w[5,:,3] = -0.25*np.sin(0.25*t)

    # First, individually
    for i in range(w.shape[2]):
        orb = CartesianOrbit.from_w(w[...,i], units=galactic)
        new_orb = orb.align_circulation_with_z()
        circ = new_orb.circulation()

        if i == 3:
            assert np.sum(circ) == 0
        else:
            assert circ[2] == 1.

    # all together now
    orb = CartesianOrbit.from_w(w, units=galactic)
    circ = orb.circulation()
    assert circ.shape == (3,4)

    new_orb = orb.align_circulation_with_z()
    new_circ = new_orb.circulation()
    assert np.all(new_circ[2,:3] == 1.)
    assert np.all(new_circ[:,3] == 0.)

# Tests below should be fixed a bit...
def test_initialize():

    with pytest.raises(ValueError):
        x = np.random.random(size=(3,10))
        v = np.random.random(size=(3,8))
        CartesianOrbit(pos=x, vel=v)

    with pytest.raises(ValueError):
        x = np.random.random(size=(3,10))
        v = np.random.random(size=(3,10))
        t = np.arange(8)
        CartesianOrbit(pos=x, vel=v, t=t)

    x = np.random.random(size=(3,10))
    v = np.random.random(size=(3,10))
    o = CartesianOrbit(pos=x, vel=v)
    assert o.ndim == 3

    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.random(size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v)
    assert o.pos.unit == u.kpc
    assert o.vel.unit == u.km/u.s

    x = np.random.random(size=(2,10))
    v = np.random.random(size=(2,10))
    o = CartesianOrbit(pos=x, vel=v)
    assert o.ndim == 2

def test_from_w():

    w = np.random.random(size=(6,10))
    o = CartesianOrbit.from_w(w, galactic)
    assert o.pos.unit == u.kpc
    assert o.vel.unit == u.kpc/u.Myr

def test_slice():

    # simple
    x = np.random.random(size=(3,10))
    v = np.random.random(size=(3,10))
    o = CartesianOrbit(pos=x, vel=v)
    new_o = o[:5]
    assert new_o.pos.shape == (3,5)

    # 1d slice on 3d
    x = np.random.random(size=(3,100,8))
    v = np.random.random(size=(3,100,8))
    t = np.arange(x.shape[1])
    o = CartesianOrbit(pos=x, vel=v, t=t)
    new_o = o[:5]
    assert new_o.pos.shape == (3,5,8)
    assert new_o.t.shape == (5,)

    # 3d slice on 3d
    o = CartesianOrbit(pos=x, vel=v, t=t)
    new_o = o[:5,:4]
    assert new_o.pos.shape == (3,5,4)
    assert new_o.t.shape == (5,)

def test_represent_as():

    # simple / unitless
    x = np.random.random(size=(3,10))
    v = np.random.random(size=(3,10))
    o = CartesianOrbit(pos=x, vel=v)
    sph_pos, sph_vel = o.represent_as(SphericalRepresentation)

    assert sph_pos.distance.unit == u.dimensionless_unscaled
    assert sph_vel.unit == u.dimensionless_unscaled

    # simple / with units
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v)
    sph_pos, sph_vel = o.represent_as(SphericalRepresentation)
    assert sph_pos.distance.unit == u.kpc

def test_to_frame():
    # simple / unitless
    x = np.random.random(size=(3,10))
    v = np.random.random(size=(3,10))
    o = CartesianOrbit(pos=x, vel=v)

    with pytest.raises(u.UnitConversionError):
        o.to_frame(Galactic)

    # simple / with units
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v)
    coo,vel = o.to_frame(Galactic)
    assert coo.name == 'galactic'

def test_w():
    # simple / unitless
    x = np.random.random(size=(3,10))
    v = np.random.random(size=(3,10))
    o = CartesianOrbit(pos=x, vel=v)
    w = o.w()
    assert w.shape == (6,10,1)

    # simple / with units
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v)
    with pytest.raises(ValueError):
        o.w()
    w = o.w(units=galactic)
    assert np.allclose(x.value, w[:3,:,0])
    assert np.allclose(v.value, (w[3:,:,0]*u.kpc/u.Myr).to(u.km/u.s).value)

    # simple / with units and potential
    p = HernquistPotential(units=galactic, m=1E11, c=0.25)
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v, potential=p)
    w = o.w()
    assert np.allclose(x.value, w[:3,:,0])
    assert np.allclose(v.value, (w[3:,:,0]*u.kpc/u.Myr).to(u.km/u.s).value)

    w = o.w(units=solarsystem)
    assert np.allclose(x.value, (w[:3,:,0]*u.au).to(u.kpc).value)
    assert np.allclose(v.value, (w[3:,:,0]*u.au/u.yr).to(u.km/u.s).value)

def test_energy():
    # with units
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v)
    KE = o.kinetic_energy()
    assert KE.unit == (o.vel.unit)**2
    assert KE.shape == o.pos.shape[1:]

    # with units and potential
    p = HernquistPotential(units=galactic, m=1E11, c=0.25)
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v, potential=p)
    PE = o.potential_energy()
    E = o.energy()

def test_angular_momentum():
    # with units
    x = np.random.random(size=(3,10))*u.kpc
    v = np.random.normal(0.,100.,size=(3,10))*u.km/u.s
    o = CartesianOrbit(pos=x, vel=v)
    L = o.angular_momentum()
    assert L.unit == (o.vel.unit*o.pos.unit)
    assert L.shape == o.pos.shape

def test_combine():

    o1 = CartesianOrbit.from_w(np.random.random(size=6), units=galactic)
    o2 = CartesianOrbit.from_w(np.random.random(size=6), units=galactic)
    o = combine(o1, o2)
    assert o.pos.shape == (3,1,2)
    assert o.vel.shape == (3,1,2)

    o1 = CartesianOrbit.from_w(np.random.random(size=(6,11,1)), units=galactic)
    o2 = CartesianOrbit.from_w(np.random.random(size=(6,11,10)), units=galactic)
    o = combine(o1, o2)
    assert o.pos.shape == (3,11,11)
    assert o.vel.shape == (3,11,11)
