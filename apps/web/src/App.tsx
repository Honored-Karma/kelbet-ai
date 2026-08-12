import { Analytics } from "@vercel/analytics/react";
import { AppProviders } from "./app/providers";

export default function App() {
  return (
    <>
      <AppProviders />
      <Analytics />
    </>
  );
}
