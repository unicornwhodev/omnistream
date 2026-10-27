"""Standalone scientific planning figure; never label it a Kit screenshot."""
import argparse
import json
from pathlib import Path
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--analysis', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('Never overwrite a retained evidence image')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Patch
    report = json.loads((args.analysis/'coverage-report.json').read_text())
    xmin, ymin, xmax, ymax = np.array(report['survey_bounds_xy_m'])/1000
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.6))
    fig.subplots_adjust(left=.065, right=.98, top=.82, bottom=.24, wspace=.23)
    cmap = ListedColormap(['#e3e8ee', '#71bc9f', '#236b68'])
    norm = BoundaryNorm([-.5, .5, 1.5, 2.5], 3)
    for ax, name, title in zip(axes, ['existing', 'overview_proposal'],
                              ['50 caméras actuelles', "50 vues aériennes proposées"]):
        with np.load(args.analysis/(name+'-samples.npz'), allow_pickle=False) as data:
            counts = np.minimum(data['multiplicity'], 2)
        pct = report['comparison'][name]['terrain_visible_fraction']*100
        ax.imshow(counts, origin='lower', extent=[xmin, xmax, ymin, ymax],
                  interpolation='nearest', cmap=cmap, norm=norm)
        for x in np.linspace(xmin, xmax, 6): ax.axvline(x, color='#324758', lw=.45, alpha=.7)
        ax.axhline((ymin+ymax)/2, color='#324758', lw=.45, alpha=.7)
        ax.set(title=f'{title}\n{pct:.2f} % des points échantillonnés', xlabel='Est local (km)',
               ylabel='Nord local (km)', xlim=(xmin, xmax), ylim=(ymin, ymax))
    fig.suptitle('Die–Justin · couverture estimée sur le relief\n'
                 'Calcul CPU — pas une capture Omniverse', fontsize=15)
    fig.legend(handles=[Patch(color=cmap(0), label='Non couvert'),
                        Patch(color=cmap(1), label='Une vue'),
                        Patch(color=cmap(2), label='Deux vues ou plus')],
               loc='lower center', bbox_to_anchor=(.5, .015), ncol=3, frameon=False)
    fig.supxlabel(f"Échantillons tous les {report['ground_sample_spacing_m']:g} m · "
                  f"rayons tous les {report['maximum_horizontal_los_sample_spacing_m']:g} m au plus\n"
                  'Arbres, bâtiments, fumée et visibilité des flammes non vérifiés', fontsize=10, y=.09)
    fig.savefig(args.output, dpi=130, metadata={'Software': 'FireViewer CPU coverage planner'})
    plt.close(fig)


if __name__ == '__main__': main()
