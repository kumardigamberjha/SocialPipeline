import type { DayTimingStat, UploadTimingAnalysis } from "./youtubeProspectsApi";

export type PeakSlotStatus = "VALID_PEAK" | "SPARSE_DATA" | "NO_SIGNIFICANT_PEAK" | "NO_DATA";

export interface DerivedPeakTiming {
  status: PeakSlotStatus;
  hasTimingData: boolean;

  /** The qualified peak day, or null if no day qualified */
  peakDay: string | null;
  /** Short name of the qualified peak day e.g. "Wed", or null */
  peakDayShort: string | null;
  /** The candidate day evaluated (highest velocity day with uploads) */
  candidateDay: DayTimingStat | null;

  /** Velocity multiplier for the candidate/peak day */
  multiplier: number;
  /** Upload count for the candidate/peak day */
  sampleCount: number;

  /** Header badge text */
  badgeText: string;
  /** Primary UI card title */
  cardTitle: string;
  /** Explanatory paragraph */
  summaryText: string;
  /** Multiplier display string e.g. "1.85×" or "—" */
  multiplierDisplay: string;
  /** Subtitle note under the multiplier */
  multiplierSubtext: string;

  /** Helper to check if a specific day is the qualified peak day */
  isPeakDay: (dayName: string) => boolean;
}

/**
 * Dynamically evaluates upload timing metrics and determines the optimal
 * release window / peak day strictly according to statistical rigor:
 *
 * 1. Never labels a day as "Peak Slot", "Optimal Release Window", or "Best" if
 *    its view velocity ratio is <= 1.0x.
 * 2. Dynamically selects the candidate day with the highest view velocity ratio.
 * 3. Requires n >= 3 uploads on the candidate day with ratio > 1.0x to declare a Peak Slot.
 * 4. If n < 3, labels as "Sparse Data / Inconclusive".
 * 5. If all days are <= 1.0x, labels as "No Statistically Significant Peak Slot".
 * 6. Guarantees zero hardcoded day fallbacks.
 */
export function derivePeakTiming(timing?: UploadTimingAnalysis | null): DerivedPeakTiming {
  const defaultInsufficient: DerivedPeakTiming = {
    status: "NO_DATA",
    hasTimingData: false,
    peakDay: null,
    peakDayShort: null,
    candidateDay: null,
    multiplier: 0,
    sampleCount: 0,
    badgeText: "Sparse Data / Inconclusive",
    cardTitle: "Peak Slot: Insufficient Data",
    summaryText: "Upload volume is too sparse across historical days to reliably recommend an optimal release window.",
    multiplierDisplay: "—",
    multiplierSubtext: "no timing data",
    isPeakDay: () => false,
  };

  if (!timing || !timing.has_timing_data || !timing.days || timing.days.length === 0) {
    return defaultInsufficient;
  }

  // Filter for days that have at least one upload
  const activeDays = timing.days.filter((d) => d.video_count > 0);
  if (activeDays.length === 0) {
    return {
      ...defaultInsufficient,
      hasTimingData: true,
      multiplierSubtext: "no uploads recorded",
    };
  }

  // Dynamically determine candidate day: highest view velocity ratio relative to baseline
  // Break ties by sample size (video_count), then avg_views
  const sortedDays = [...activeDays].sort((a, b) => {
    if (b.multiplier !== a.multiplier) {
      return b.multiplier - a.multiplier;
    }
    if (b.video_count !== a.video_count) {
      return b.video_count - a.video_count;
    }
    return b.avg_views - a.avg_views;
  });

  const candidate = sortedDays[0];

  // Case 1: All days have a view velocity ratio <= 1.0x
  if (candidate.multiplier <= 1.0) {
    return {
      status: "NO_SIGNIFICANT_PEAK",
      hasTimingData: true,
      peakDay: null,
      peakDayShort: null,
      candidateDay: candidate,
      multiplier: candidate.multiplier,
      sampleCount: candidate.video_count,
      badgeText: "No Statistically Significant Peak Slot",
      cardTitle: "Peak Slot: Insufficient Data",
      summaryText: "Upload volume is too sparse across historical days to reliably recommend an optimal release window.",
      multiplierDisplay: "—",
      multiplierSubtext: "all days ≤ 1.0× median",
      isPeakDay: () => false,
    };
  }

  // Case 2: Candidate has velocity ratio > 1.0x but upload count (n) < 3
  if (candidate.video_count < 3) {
    return {
      status: "SPARSE_DATA",
      hasTimingData: true,
      peakDay: null,
      peakDayShort: null,
      candidateDay: candidate,
      multiplier: candidate.multiplier,
      sampleCount: candidate.video_count,
      badgeText: "Sparse Data / Inconclusive",
      cardTitle: "Peak Slot: Insufficient Data",
      summaryText: "Upload volume is too sparse across historical days to reliably recommend an optimal release window.",
      multiplierDisplay: "—",
      multiplierSubtext: `n=${candidate.video_count} (below n=3 threshold)`,
      isPeakDay: () => false,
    };
  }

  // Case 3: Valid Peak (ratio > 1.0x AND n >= 3)
  const timeSlot =
    timing.best_window?.slot_confident && timing.best_window?.best_time_slot
      ? timing.best_window.best_time_slot.split(" (")[0]
      : null;

  const cardTitle = timeSlot ? `${candidate.day} • ${timeSlot}` : candidate.day;

  const summaryText = `Publish on ${candidate.day}. Historical velocity indicates ${candidate.multiplier}x above channel median across ${candidate.video_count} uploads.${
    timeSlot ? ` Best observed window: ${timeSlot}.` : ""
  }`;

  return {
    status: "VALID_PEAK",
    hasTimingData: true,
    peakDay: candidate.day,
    peakDayShort: candidate.day_short,
    candidateDay: candidate,
    multiplier: candidate.multiplier,
    sampleCount: candidate.video_count,
    badgeText: "Optimal Release Window",
    cardTitle,
    summaryText,
    multiplierDisplay: `${candidate.multiplier}×`,
    multiplierSubtext: `n=${candidate.video_count} · vs median`,
    isPeakDay: (dayName: string) => dayName.toLowerCase() === candidate.day.toLowerCase(),
  };
}
