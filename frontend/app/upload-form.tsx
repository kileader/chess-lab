'use client';

import { useRouter } from 'next/navigation';
import { FormEvent, useState } from 'react';
import { apiFetch } from '../lib/api-client';
import { practiceError } from './practice-position';

type ImportSummary = {
  games_received: number;
  games_added: number;
  duplicates_skipped: number;
};


export function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  async function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;

    setIsUploading(true);
    setSummary(null);
    setError(null);
    const body = new FormData();
    body.append('file', file);

    try {
      const response = await apiFetch('/api/games/import', {
        method: 'POST',
        body,
      });
      if (!response.ok) throw new Error(await practiceError(response, 'The archive could not be imported.'));
      setSummary(await response.json() as ImportSummary);
      router.refresh();
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Upload failed.');
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <form className="upload-form" onSubmit={submitUpload}>
      <label className="file-picker">
        <input
          accept=".pgn,application/x-chess-pgn,text/plain"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          type="file"
        />
        <span>{file?.name ?? 'Choose a PGN archive'}</span>
      </label>
      <button disabled={!file || isUploading} type="submit">
        {isUploading ? 'Importing…' : 'Import games'}
      </button>
      <small>Private to your account. Up to 10 MB and 5,000 games per import.</small>
      {summary && (
        <p className="upload-result" role="status">
          {summary.games_added.toLocaleString()} added · {summary.duplicates_skipped.toLocaleString()} already present
        </p>
      )}
      {error && <p className="upload-error" role="alert">{error}</p>}
    </form>
  );
}
