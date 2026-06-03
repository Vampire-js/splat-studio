import Uploader from '@/components/Uploader';

export default function HomePage() {
  return (
    <main>
      <h1>Splat Studio</h1>
      <p style={{ opacity: 0.8 }}>
        Upload a set of photos of an object and we&apos;ll turn it into an embeddable
        3D Gaussian Splat — no mesh, no manual modelling.
      </p>
      <Uploader />
    </main>
  );
}
