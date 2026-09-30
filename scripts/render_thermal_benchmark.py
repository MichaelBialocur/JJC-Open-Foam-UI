"""Render the committed measured benchmark summary (requires Matplotlib)."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, PercentFormatter

root = Path(__file__).resolve().parents[1]
data = json.loads((root/'docs/thermal-benchmarks.json').read_text())
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
fig, axes = plt.subplots(1,2,figsize=(10,3.6),layout='constrained')
profile = data['fine_temperature_profile']
x = [p['x_m']*1000 for p in profile]
axes[0].plot(x,[p['bulk_temperature_c'] for p in profile],color='#1671b8',lw=2,label='Mixing temperature')
axes[0].plot(x,[p['wall_temperature_c'] for p in profile],color='#c07514',lw=2,label='Inner-wall temperature')
axes[0].set(xlabel='Axial position (mm)',ylabel='Temperature (°C)',xlim=(0,1000),ylim=(20,25),title='Computed temperature · fine mesh')
axes[0].xaxis.set_major_locator(MultipleLocator(200));axes[0].yaxis.set_major_locator(MultipleLocator(1))
axes[0].legend(frameon=False,loc='upper left')
rows=data['results']
axes[1].bar([r['mesh'].title() for r in rows],[r['nusselt_error_percent'] for r in rows],color=['#aac5dc','#5b9ec5','#246e9c'],width=.55)
axes[1].set(ylabel='Deviation from Nu = 48/11',ylim=(0,1),title='Thermal refinement · analytical check')
axes[1].yaxis.set_major_locator(MultipleLocator(.2));axes[1].yaxis.set_major_formatter(PercentFormatter(xmax=100,decimals=1))
for i,row in enumerate(rows):axes[1].text(i,row['nusselt_error_percent']+.035,f"{row['nusselt_error_percent']:.3f}%",ha='center',fontsize=10)
for ax in axes:
    ax.set_axisbelow(True);ax.grid(axis='y',color='#dce4eb',lw=.7)
    ax.spines[['top','right']].set_visible(False)
fig.savefig(root/'docs/thermal-comparison.svg')
