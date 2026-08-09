/** PKR formatting */
export function fmt(n) {
  return n || n === 0 ? 'PKR ' + Number(n).toLocaleString('en-PK') : 'PKR 0';
}

export function fmtShort(n) {
  if (!n) return 'PKR 0';
  if (n >= 10000000) return 'PKR ' + (n / 10000000).toFixed(1) + 'Cr';
  if (n >= 100000) return 'PKR ' + (n / 100000).toFixed(1) + 'L';
  return 'PKR ' + Number(n).toLocaleString('en-PK');
}

export function instStatusBadge(status) {
  if (status === 'paid') return 'bg-green';
  if (status === 'overdue') return 'bg-red';
  if (status === 'partial') return 'bg-orange';
  return 'bg-yellow';
}

export function overdueBadge(days) {
  if (days >= 61) return 'bg-red';
  if (days >= 31) return 'bg-orange';
  return 'bg-yellow';
}
