/** Hand what is at an address the page holds (an object URL, a data URL) to the browser to save. */
export function saveUrl(url: string, name: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
}

/** Hand a file's content to the browser to save under a name. */
export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  saveUrl(url, name);
  // The download has started by then
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
