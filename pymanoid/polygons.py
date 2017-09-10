#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2017 Stephane Caron <stephane.caron@normalesup.org>
#
# This file is part of pymanoid <https://github.com/stephane-caron/pymanoid>.
#
# pymanoid is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# pymanoid is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# pymanoid. If not, see <http://www.gnu.org/licenses/>.

from __future__ import division

from numpy import array, dot, hstack
from scipy.spatial import ConvexHull

from misc import norm
from polyhedra import compute_chebyshev_center


PREC_TOL = 1e-10  # tolerance to numerical imprecisions


def __compute_polygon_hull(B, c):
    """
    Compute the vertex representation of a polygon defined by:

    .. math::

        B x \\leq c

    where `x` is a 2D vector.

    Parameters
    ----------
    B : array, shape=(2, K)
        Linear inequality matrix.
    c : array, shape=(K,)
        Linear inequality vector with positive coordinates.

    Returns
    -------
    vertices : list of arrays
        List of 2D vertices in counterclowise order.

    Notes
    -----
    The origin [0, 0] should lie inside the polygon (:math:`c \\geq 0`) in order
    to build the polar form. If you don't have this guarantee, call
    ``compute_polar_polygon()`` instead.

    Checking that :math:`c > 0` is not optional. The rest of the algorithm can
    be executed when some coordinates :math:`c_i < 0`, but the result would be
    wrong.
    """
    assert B.shape[1] == 2, \
        "Input (B, c) is not a polygon: B.shape = %s" % str(B.shape)
    assert all(c > 0), \
        "Polygon should contain the origin, but min(c) = %.2f" % min(c)

    B_polar = hstack([
        (B[:, column] * 1. / c).reshape((B.shape[0], 1))
        for column in xrange(2)])

    def axis_intersection(i, j):
        ai, bi = c[i], B[i]
        aj, bj = c[j], B[j]
        x = (ai * bj[1] - aj * bi[1]) * 1. / (bi[0] * bj[1] - bj[0] * bi[1])
        y = (bi[0] * aj - bj[0] * ai) * 1. / (bi[0] * bj[1] - bj[0] * bi[1])
        return array([x, y])

    # QHULL OPTIONS:
    #
    # - ``Pp`` -- do not report precision problems
    # - ``Q0`` -- no merging with C-0 and Qx
    #
    # ``Q0`` avoids [this bug](https://github.com/scipy/scipy/issues/6484).
    # It slightly diminishes computation times (0.9 -> 0.8 ms on my machine)
    # but raises QhullError at the first sight of precision errors.
    #
    hull = ConvexHull([row for row in B_polar], qhull_options='Pp Q0')
    #
    # contrary to hull.simplices (which was not in practice), hull.vertices is
    # guaranteed to be in counterclockwise order for 2-D (see scipy doc)
    #
    simplices = [(hull.vertices[i], hull.vertices[i + 1])
                 for i in xrange(len(hull.vertices) - 1)]
    simplices.append((hull.vertices[-1], hull.vertices[0]))
    vertices = [axis_intersection(i, j) for (i, j) in simplices]
    return vertices


def compute_polygon_hull(B, c):
    """
    Compute the vertex representation of a polygon defined by:

    .. math::

        B x \leq c

    where `x` is a 2D vector.

    Parameters
    ----------
    B : array, shape=(2, K)
        Linear inequality matrix.
    c : array, shape=(K,)
        Linear inequality vector.

    Returns
    -------
    vertices : list of arrays
        List of 2D vertices in counterclockwise order.
    """
    x = None
    if not all(c > 0):
        x = compute_chebyshev_center(B, c)
        c = c - dot(B, x)
    if not all(c > 0):
        raise Exception("Polygon is empty (min. dist. to edge %.2f)" % min(c))
    vertices = __compute_polygon_hull(B, c)
    if x is not None:
        vertices = [v + x for v in vertices]
    return vertices


def intersect_line_polygon(line, vertices, apply_hull):
    """
    Intersect a line segment with a polygon.

    Parameters
    ----------
    line : couple of arrays
        End points of the line segment (2D or 3D).
    vertices : list of arrays
        Vertices of the polygon.
    apply_hull : bool
        Set to `True` to apply a convex hull algorithm to `vertices`. Otherwise,
        the function assumes that vertices are already sorted in clockwise or
        counterclockwise order.

    Returns
    -------
    inter_points : list of array
        List of intersection points between the line segment and the polygon.

    Notes
    -----
    This code is adapted from <http://stackoverflow.com/a/20679579>. With
    `apply_hull=True`, this variant %timeits around 90 us on my machine, vs. 170
    us when using the Shapely library <http://toblerity.org/shapely/> (the
    latter variant was removed by commit a8a267b). On the same setting with
    `apply_hull=False`, it %timeits to 6 us.
    """
    def line_coordinates(p1, p2):
        A = (p1[1] - p2[1])
        B = (p2[0] - p1[0])
        C = (p1[0] * p2[1] - p2[0] * p1[1])
        return A, B, -C

    def intersection(L1, L2):
        D = L1[0] * L2[1] - L1[1] * L2[0]
        Dx = L1[2] * L2[1] - L1[1] * L2[2]
        Dy = L1[0] * L2[2] - L1[2] * L2[0]
        if abs(D) < 1e-5:
            return None
        x = Dx / D
        y = Dy / D
        return x, y

    if apply_hull:
        points = vertices
        hull = ConvexHull(points)
        vertices = [points[i] for i in hull.vertices]

    n = len(vertices)
    p1, p2 = line
    L1 = line_coordinates(p1, p2)
    x_min, x_max = min(p1[0], p2[0]), max(p1[0], p2[0])
    y_min, y_max = min(p1[1], p2[1]), max(p1[1], p2[1])
    inter_points = []
    for i, v1 in enumerate(vertices):
        v2 = vertices[(i + 1) % n]
        L2 = line_coordinates(v1, v2)
        p = intersection(L1, L2)
        if p is not None:
            if not (x_min <= p[0] <= x_max and y_min <= p[1] <= y_max):
                continue
            vx_min, vx_max = min(v1[0], v2[0]), max(v1[0], v2[0])
            vy_min, vy_max = min(v1[1], v2[1]), max(v1[1], v2[1])
            if not (vx_min - PREC_TOL <= p[0] <= vx_max + PREC_TOL and
                    vy_min - PREC_TOL <= p[1] <= vy_max + PREC_TOL):
                continue
            inter_points.append(array(p))
    return inter_points


def intersect_line_cylinder(line, vertices):
    """
    Intersect the line segment [p1, p2] with a vertical cylinder of polygonal
    cross-section. If the intersection has two points, returns the one closest
    to p1.

    Parameters
    ----------
    line : couple of (3,) arrays
        End points of the 3D line segment.
    vertices : list of (3,) arrays
        Vertices of the polygon.

    Returns
    -------
    inter_points : list of (3,) arrays
        List of intersection points between the line segment and the cylinder.
    """
    inter_points = []
    inter_2d = intersect_line_polygon(line, vertices, apply_hull=True)
    for p in inter_2d:
        p1, p2 = array(line[0]), array(line[1])
        alpha = norm(p - p1[:2]) / norm(p2[:2] - p1[:2])
        z = p1[2] + alpha * (p2[2] - p1[2])
        inter_points.append(array([p[0], p[1], z]))
    return inter_points


def intersect_polygons(polygon1, polygon2):
    """
    Intersect two polygons.

    Parameters
    ----------
    polygon1 : list of arrays
        Vertices of the first polygon in counterclockwise order.
    polygon1 : list of arrays
        Vertices of the second polygon in counterclockwise order.

    Returns
    -------
    intersection : list of arrays
        Vertices of the intersection in counterclockwise order.
    """
    from pyclipper import Pyclipper, PT_CLIP, PT_SUBJECT, CT_INTERSECTION
    from pyclipper import scale_to_clipper, scale_from_clipper
    # could be accelerated by removing the scale_to/from_clipper()
    subj, clip = (polygon1,), polygon2
    pc = Pyclipper()
    pc.AddPath(scale_to_clipper(clip), PT_CLIP)
    pc.AddPaths(scale_to_clipper(subj), PT_SUBJECT)
    solution = pc.Execute(CT_INTERSECTION)
    if not solution:
        return []
    return scale_from_clipper(solution)[0]
