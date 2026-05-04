import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter


def generate_simulated_groove(num_points=1000, x_range=(0, 50), y_range=(0, 50)):
    """Generate gridded raster scan data (CNC-like, not random).
    
    RASTER SCAN MODE:
    - X, Y: Regular grid from meshgrid (simulates line-by-line CNC motion)
    - Z: Base 10 mm + groove feature (20-30mm width, 3mm depth) + 0.1mm Gaussian noise
    """
    # Generate square grid
    grid_size = int(np.sqrt(num_points))
    x_grid = np.linspace(x_range[0], x_range[1], grid_size)
    y_grid = np.linspace(y_range[0], y_range[1], grid_size)
    X, Y = np.meshgrid(x_grid, y_grid)
    
    x_data = X.flatten()
    y_data = Y.flatten()
    
    # Base height: 10 mm
    z_data = np.full(len(x_data), 10.0)
    
    # Groove feature: 20 < X < 30 → Z drops by 3 mm
    groove_mask = (x_data > 20) & (x_data < 30)
    z_data[groove_mask] -= 3.0
    
    # Add sensor noise
    noise = np.random.normal(0, 0.1, len(x_data))
    z_data += noise
    
    df = pd.DataFrame({'x': x_data, 'y': y_data, 'z': z_data})
    return df


def save_csv(df, path):
    df.to_csv(path, index=False)


def load_csv(path):
    return pd.read_csv(path)


def fit_grid(df, grid_res=100, method='cubic'):
    xi = np.linspace(df['x'].min(), df['x'].max(), grid_res)
    yi = np.linspace(df['y'].min(), df['y'].max(), grid_res)
    grid_x, grid_y = np.meshgrid(xi, yi)
    points = (df['x'].values, df['y'].values)
    grid_z = griddata(points, df['z'].values, (grid_x, grid_y), method=method)
    return grid_x, grid_y, grid_z


def plot_surface(grid_x, grid_y, grid_z, out_path=None, title='3D Surface', apply_filter=True):
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    
    # Apply smoothing filter for cleaner rendering
    if apply_filter:
        grid_z = gaussian_filter(grid_z, sigma=2.5)
    
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    surf = ax.plot_surface(grid_x, grid_y, grid_z, cmap='viridis', edgecolor='none', alpha=0.9)
    ax.set_title(title)
    ax.set_xlabel('X Axis (mm)')
    ax.set_ylabel('Y Axis (mm)')
    ax.set_zlabel('Z Axis (Height/mm)')
    fig.colorbar(surf, shrink=0.5, aspect=5, label='Height (mm)')
    if out_path:
        fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description='Simulate laser scan, fit grid, export CSV/PNG')
    sub = parser.add_subparsers(dest='cmd')

    g = sub.add_parser('generate')
    g.add_argument('--out', required=True, help='output CSV path')
    g.add_argument('--points', type=int, default=1000)

    f = sub.add_parser('fit')
    f.add_argument('--in', dest='infile', required=True, help='input CSV path')
    f.add_argument('--out', dest='outimg', required=True, help='output PNG path')
    f.add_argument('--grid', type=int, default=200)
    f.add_argument('--method', choices=['linear', 'cubic', 'nearest'], default='cubic')

    b = sub.add_parser('both')
    b.add_argument('--out', required=True, help='output CSV path')
    b.add_argument('--img', required=True, help='output PNG path')
    b.add_argument('--points', type=int, default=1000)
    b.add_argument('--grid', type=int, default=200)

    args = parser.parse_args()

    if args.cmd == 'generate':
        df = generate_simulated_groove(num_points=args.points)
        save_csv(df, args.out)
        print(f'Generated {len(df)} points and saved to {args.out}')

    elif args.cmd == 'fit':
        df = load_csv(args.infile)
        grid_x, grid_y, grid_z = fit_grid(df, grid_res=args.grid, method=args.method)
        plot_surface(grid_x, grid_y, grid_z, out_path=args.outimg)
        print(f'Fitted grid and saved image to {args.outimg}')

    elif args.cmd == 'both':
        df = generate_simulated_groove(num_points=args.points)
        save_csv(df, args.out)
        grid_x, grid_y, grid_z = fit_grid(df, grid_res=args.grid)
        plot_surface(grid_x, grid_y, grid_z, out_path=args.img)
        print(f'Generated CSV {args.out} and image {args.img}')

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
