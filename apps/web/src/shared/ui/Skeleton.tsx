export function Skeleton({ height = 16, width = "100%" }: { height?: number | string; width?: number | string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden />;
}

export function SkeletonBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} height={index === 0 ? 28 : 14} width={index === 0 ? "60%" : "100%"} />
      ))}
    </div>
  );
}
