import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link className="button button--secondary button--lg" to="/docs/overview">
            Start with the five-minute overview
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title="Documentation"
      description="Reliable FastAPI services from the EVA template">
      <HomepageHeader />
      <main>
        <section className="container padding-vert--lg">
          <div className="row">
            <div className="col col--4">
              <h2>Generate</h2>
              <p>Choose a deterministic profile and create a service with the nk CLI.</p>
            </div>
            <div className="col col--4">
              <h2>Operate</h2>
              <p>Understand identity, data, queues, AI, deployment, and observability boundaries.</p>
            </div>
            <div className="col col--4">
              <h2>Verify</h2>
              <p>Use contracts, health checks, OpenAPI, and reproducible CI before release.</p>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
