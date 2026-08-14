/**
 * Pull the first http(s) URL out of a Web Share Target GET request.
 *
 * Android apps are inconsistent about which field carries the link: some put
 * it in `url`, many (YouTube, Instagram) embed it somewhere inside `text`.
 */
export function extractSharedUrl(params: URLSearchParams): string | null {
  for (const field of ["url", "text"]) {
    const match = params.get(field)?.match(/https?:\/\/\S+/);
    if (match) return match[0];
  }
  return null;
}
