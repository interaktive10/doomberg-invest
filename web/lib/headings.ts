export type HeadingTag = "h1" | "h2" | "h3" | "h4" | "h5" | "h6";

/** The tag for a markdown heading of `level` rendered under a page heading of level `below` (a Section's h2): the
 * card's "# Title" becomes an h3, so a page keeps one h1 and its outline (the thesis page showed two h1s). */
export function shiftedHeading(level: 1 | 2 | 3 | 4 | 5 | 6, below = 2): HeadingTag {
  return `h${Math.min(6, level + below)}` as HeadingTag;
}
