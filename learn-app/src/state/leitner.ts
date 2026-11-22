// [origin ref=llm-dsl-gu1y.7 req=REQ-OPERATOR-EDU-009 c4=learn_app/learn_server]
//   [intent]Pure Leitner box transition: all-correct moves up one box (max 5), any wrong drops to box 1, due = today + interval for the new box.[/intent]
//   [inv]Takes today as a YYYY-MM-DD parameter; never reads the clock.[/inv]
// [/origin]
export const INTERVAL_DAYS = [0, 1, 2, 4, 8, 16] as const;
export const MAX_BOX = 5;

export function addDays(day: string, n: number): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error(`today must be YYYY-MM-DD, got ${JSON.stringify(day)}`);
  const d = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) throw new Error(`today is not a valid date: ${day}`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function leitner(box: number, allCorrect: boolean, today: string): { box: number; due: string } {
  const next = allCorrect ? Math.min(MAX_BOX, box + 1) : 1;
  return { box: next, due: addDays(today, INTERVAL_DAYS[next]) };
}
