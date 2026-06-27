/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: o portal é só HTML/JS estático servido pelo Netlify (sem runtime).
  output: "export",
  images: { unoptimized: true },
  // Lê os artefatos JSON da raiz do repo no build; nada de rede em runtime.
};

export default nextConfig;
