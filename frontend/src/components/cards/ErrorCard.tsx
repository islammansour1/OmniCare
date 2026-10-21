import { Badge } from '../ui/Badge';
import { AlertIcon } from '../ui/icons';
import type { ErrorData } from '../../lib/types';

export function ErrorCard({ data }: { data: ErrorData }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4"
    >
      <AlertIcon className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-rose-800">{data.detail}</p>
          {data.code ? <Badge tone="rose">{data.code}</Badge> : null}
        </div>
      </div>
    </div>
  );
}
