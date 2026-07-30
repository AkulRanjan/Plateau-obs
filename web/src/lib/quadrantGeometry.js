import { NOVELTY_FLOOR } from "../data/trace.js";

/* Geometry for the quadrant map, kept in a plain module so it can be asserted
 * from a node script as well as rendered. Position IS data here, so the mapping
 * gets tested rather than eyeballed. */

export const SZ = 300;
export const PAD = 34;
export const IW = SZ - PAD * 2;

/** Observation novelty → x. Left edge = learned nothing. */
export const xOfNovelty = (nov) => PAD + IW * nov;

/** Action similarity → y, inverted so that high similarity sits high. */
export const yOfSimilarity = (sim) => PAD + IW * (1 - sim);

/**
 * Which quadrant a point falls in, derived purely from its coordinates and the
 * two thresholds.
 *
 * This must always agree with the label deriveState assigned to the same turn.
 * If it ever disagrees, a dot is drawn in a region that contradicts its own
 * colour — which is the one class of bug this chart cannot survive, because the
 * whole claim is that position and state say the same thing.
 */
export function quadrantAt(nov, sim, ceiling) {
  const stagnant = nov < NOVELTY_FLOOR;
  const confident = sim >= ceiling;
  if (stagnant) return confident ? "stuck" : "thrash";
  return confident ? "batch" : "productive";
}
