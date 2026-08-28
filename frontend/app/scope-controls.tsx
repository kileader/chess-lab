'use client';

import { useState } from 'react';

type Props = {
  minYear: number;
  maxYear: number;
  dateFrom?: string;
  dateTo?: string;
  color: 'all' | 'white' | 'black';
  grouping: 'family' | 'variation';
  filteredGames: number;
  totalGames: number;
};

function queryFor(values: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => value && query.set(key, value));
  return `/?${query}`;
}

function apiDate(date: Date) {
  return date.toISOString().slice(0, 10).replaceAll('-', '.');
}

export function ScopeControls({
  minYear,
  maxYear,
  dateFrom,
  dateTo,
  color: initialColor,
  grouping: initialGrouping,
  filteredGames,
  totalGames,
}: Props) {
  const [startYear, setStartYear] = useState(Number(dateFrom?.slice(0, 4)) || minYear);
  const [endYear, setEndYear] = useState(Number(dateTo?.slice(0, 4)) || maxYear);
  const [color, setColor] = useState(initialColor);
  const [grouping, setGrouping] = useState(initialGrouping);
  const today = new Date();
  const yearAgo = new Date(today);
  yearAgo.setUTCFullYear(yearAgo.getUTCFullYear() - 1);
  const twoYearsAgo = new Date(today);
  twoYearsAgo.setUTCFullYear(twoYearsAgo.getUTCFullYear() - 2);

  const shared = {
    color: color === 'all' ? undefined : color,
    grouping,
  };

  function applyCustom() {
    const safeStart = Math.min(startYear, endYear);
    const safeEnd = Math.max(startYear, endYear);
    window.location.href = queryFor({
      ...shared,
      date_from: `${safeStart}.01.01`,
      date_to: `${safeEnd}.12.31`,
    });
  }

  return (
    <section className="scope-panel" aria-label="Analysis scope">
      <div className="scope-heading">
        <div><p className="eyebrow">Analysis scope</p><strong>{filteredGames.toLocaleString()} of {totalGames.toLocaleString()} games</strong></div>
        <div className="period-presets" aria-label="Time period presets">
          <a href={queryFor({ ...shared, date_from: apiDate(yearAgo) })}>Last year</a>
          <a href={queryFor({ ...shared, date_from: apiDate(twoYearsAgo) })}>Last 2 years</a>
          <a href={queryFor({ ...shared, period: 'all' })}>All time</a>
        </div>
      </div>

      <div className="scope-controls">
        <label className="scope-select">Color
          <select value={color} onChange={(event) => setColor(event.target.value as Props['color'])}>
            <option value="all">All games</option><option value="white">As White</option><option value="black">As Black</option>
          </select>
        </label>
        <label className="scope-select">Opening view
          <select value={grouping} onChange={(event) => setGrouping(event.target.value as Props['grouping'])}>
            <option value="family">Families</option><option value="variation">Variations</option>
          </select>
        </label>
        <div className="timeline-control">
          <div className="timeline-label"><span>From {Math.min(startYear, endYear)}</span><span>Through {Math.max(startYear, endYear)}</span></div>
          <div className="range-stack">
            <input aria-label="Start year" type="range" min={minYear} max={maxYear} value={startYear} onChange={(event) => setStartYear(Number(event.target.value))} />
            <input aria-label="End year" type="range" min={minYear} max={maxYear} value={endYear} onChange={(event) => setEndYear(Number(event.target.value))} />
          </div>
        </div>
        <button className="scope-apply" type="button" onClick={applyCustom}>Apply scope</button>
      </div>
    </section>
  );
}
