export type ClassValue = string | number | null | false | undefined;

/** Join class names, dropping falsy values. */
export function cn(...inputs: ClassValue[]): string {
  return inputs.filter(Boolean).join(' ');
}
