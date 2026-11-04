import { UrlMatchResult, UrlSegment } from '@angular/router';

/**
 * The route of the Knowledge base page: /knowledge-base and /knowledge-base/<slug> as one route,
 * so the page (and its list) stays when another note opens. In its own file, so the app module
 * doesn't load the page with it.
 */
export function knowledgeBaseMatcher(segments: UrlSegment[]): UrlMatchResult | null {
  if (segments.length < 1 || segments.length > 2 || segments[0].path !== 'knowledge-base') return null;
  return { consumed: segments, posParams: segments.length === 2 ? { slug: segments[1] } : {} };
}
