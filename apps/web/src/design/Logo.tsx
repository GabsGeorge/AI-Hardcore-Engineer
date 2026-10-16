/** The Getnet logo. See apps/web/NOTICE.md for the attribution of this asset. */
export function Logo({ height = 32 }: { height?: number }) {
  return (
    <img
      src="/brand/logo-getnet.png"
      alt="Getnet"
      style={{ height, width: "auto" }}
      className="shrink-0"
    />
  );
}
