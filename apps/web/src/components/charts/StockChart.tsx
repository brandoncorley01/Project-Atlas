"use client";

import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from "lightweight-charts";

export interface ChartBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

interface StockChartProps {
  bars: ChartBar[];
  entryLow?: number;
  entryHigh?: number;
  stopLoss?: number;
  profitTargets?: number[];
  height?: number;
}

export function StockChart({
  bars,
  entryLow,
  entryHigh,
  stopLoss,
  profitTargets = [],
  height = 320,
}: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!containerRef.current || bars.length === 0) {
      return;
    }

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.12)" },
        horzLines: { color: "rgba(148, 163, 184, 0.12)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    series.setData(
      bars.map((bar) => ({
        time: bar.date as Time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );

    const addLine = (price: number, color: string, title: string) => {
      const line = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        lineStyle: 2,
        title,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      const points: LineData[] = bars.map((bar) => ({
        time: bar.date as Time,
        value: price,
      }));
      line.setData(points);
    };

    if (entryLow != null) addLine(entryLow, "#38bdf8", "Entry low");
    if (entryHigh != null) addLine(entryHigh, "#0ea5e9", "Entry high");
    if (stopLoss != null) addLine(stopLoss, "#ef4444", "Stop");
    profitTargets.forEach((target, index) => {
      addLine(target, "#22c55e", `Target ${index + 1}`);
    });

    chart.timeScale().fitContent();
    chartRef.current = chart;
    seriesRef.current = series;

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) {
        chart.applyOptions({ width });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [bars, entryLow, entryHigh, stopLoss, profitTargets, height]);

  if (bars.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted">
        No chart data available
      </div>
    );
  }

  return <div ref={containerRef} className="w-full overflow-hidden rounded-xl border border-border" />;
}
