import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption } from 'echarts/core'
import { tokens, type Tokens } from './theme'

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

/** Options communes : typographie Yas, grille discrète, tooltip aux couleurs du thème, animation courte. */
export function base(t: Tokens): EChartsCoreOption {
  return {
    color: t.series, backgroundColor: 'transparent',
    textStyle: { fontFamily: 'Figtree, system-ui, sans-serif', color: t.muted },
    animationDuration: 400,
    tooltip: {
      backgroundColor: t.surface, borderColor: t.line, textStyle: { color: t.ink, fontSize: 12 }, extraCssText: 'box-shadow:0 6px 20px rgba(0,0,0,.15)',
    },
    legend: { textStyle: { color: t.muted }, icon: 'roundRect', itemWidth: 10, itemHeight: 10, top: 0 },
  }
}

export const axis = (t: Tokens, extra: object = {}) => ({
  axisLine: { lineStyle: { color: t.line } }, axisTick: { show: false },
  axisLabel: { color: t.muted, fontSize: 11 }, splitLine: { lineStyle: { color: t.line, opacity: 0.7 } }, ...extra,
})

/** Graphique ECharts : `build` reçoit les tokens du thème actif et renvoie les options. */
export function Chart({ build, height = 280, onClick, label }: {
  build: (t: Tokens) => EChartsCoreOption; height?: number; onClick?: (p: any) => void; label?: string
}) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const click = useRef(onClick)
  click.current = onClick

  useEffect(() => {
    const c = echarts.init(el.current!, undefined, { renderer: 'canvas' })
    chart.current = c
    c.on('click', (p) => click.current?.(p))
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(el.current!)
    return () => { ro.disconnect(); c.dispose(); chart.current = null }
  }, [])

  useEffect(() => {
    const t = tokens()
    chart.current?.setOption({ ...base(t), ...build(t) }, true)
  })

  return <div ref={el} role="img" aria-label={label} style={{ height, width: '100%' }} />
}
