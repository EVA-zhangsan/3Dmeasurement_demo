from __future__ import annotations

import numpy as np

try:
    import open3d as o3d
except Exception as exc:  # pragma: no cover - import error becomes a runtime error in the GUI
    o3d = None
    OPEN3D_IMPORT_ERROR = exc
else:
    OPEN3D_IMPORT_ERROR = None


def ensure_points_array(points) -> np.ndarray:
    """Normalize input to a float64 Nx3 numpy array."""
    array = np.asarray(points, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError('points must be an Nx3 array')
    return array


def statistical_outlier_removal(points, nb_neighbors: int, std_ratio: float) -> np.ndarray:
    """Apply Open3D Statistical Outlier Removal to Nx3 points.

    Returns the filtered points. If Open3D is unavailable, raises a clear error.
    If the cloud is too small or filtering removes everything, returns the input.
    """
    if o3d is None:
        raise RuntimeError(f'Open3D is not available: {OPEN3D_IMPORT_ERROR}')

    array = ensure_points_array(points)
    if len(array) <= max(3, nb_neighbors):
        return array

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(array)

    filtered_cloud, _ = cloud.remove_statistical_outlier(
        nb_neighbors=int(nb_neighbors),
        std_ratio=float(std_ratio),
    )
    filtered = np.asarray(filtered_cloud.points, dtype=np.float64)
    return filtered if len(filtered) else array
