from __future__ import annotations

import numpy as np

try:
    import open3d as o3d
except Exception as exc:  # pragma: no cover - runtime dependency guard
    raise SystemExit(f'Open3D is required to generate the target: {exc}')


def main() -> None:
    x = np.arange(0, 50.0, 0.5)
    y = np.arange(0, 50.0, 0.5)
    xx, yy = np.meshgrid(x, y)

    zz = np.full_like(xx, 10.0, dtype=np.float64)
    groove_mask = (xx > 20.0) & (xx < 30.0)
    zz[groove_mask] -= 3.0
    zz += np.random.normal(0.0, 0.05, zz.shape)

    points = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points)

    out_path = 'standard_groove.ply'
    o3d.io.write_point_cloud(out_path, cloud)
    print('标准凹槽靶标生成完毕: standard_groove.ply')
    print('理论槽深: 3.0 mm')
    print('理论槽宽: 10.0 mm')


if __name__ == '__main__':
    main()