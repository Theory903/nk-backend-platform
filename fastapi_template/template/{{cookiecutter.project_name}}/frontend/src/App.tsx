import {
  ArrowRight,
  Check,
  ChevronDown,
  Clock3,
  Code2,
  Copy,
  Menu,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import {
  type Endpoint,
  type OpenApiDocument,
  groupByTag,
  parseEndpoints,
  schemaTypeLabel,
} from "@/lib/openapi";
import { useStudio } from "@/hooks/use-studio";
import type { StudioApi } from "@/hooks/use-studio";
import { AuthCard } from "@/components/auth-card";
import { RequestBar } from "@/components/request-bar";
import { RequestPanel } from "@/components/request-panel";

const codeSamples = {
  dependency: `<dependency>
   <groupId>org.springdoc</groupId>
   <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
   <version>2.0.2</version>
</dependency>`,
  properties: `springdoc.swagger-ui.disable-swagger-default-url=true
springdoc.swagger-ui.path=/myproject`,
  configuration: `@Component
public class SwaggerConfiguration implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(final ApplicationPreparedEvent event) {
        ConfigurableEnvironment environment = event.getApplicationContext().getEnvironment();
        Properties props = new Properties();
        props.put("springdoc.swagger-ui.path", swaggerPath());
        environment.getPropertySources()
          .addFirst(new PropertiesPropertySource("programmatically", props));
    }

    private String swaggerPath() {
        return "/myproject"; // TODO: implement your logic here.
    }
}`,
  listener: `public static void main(String[] args) {
    SpringApplication application = new SpringApplication(SampleApplication.class);
    application.addListeners(new SwaggerConfiguration());
    application.run(args);
}`,
  springfoxDependency: `<dependency>
    <groupId>io.springfox</groupId>
    <artifactId>springfox-swagger2</artifactId>
    <version>3.0.0</version>
</dependency>`,
  docket: `@Bean
public Docket api() {
    return new Docket(DocumentationType.SWAGGER_2)
      .select()
      .apis(RequestHandlerSelectors.any())
      .paths(PathSelectors.any())
      .build();
}

@Override
public void addViewControllers(ViewControllerRegistry registry) {
   registry.addRedirectViewController("/myproject", "/");
}`,
  redirect: `@Controller
public class SwaggerController {

@RequestMapping("/myproject")
public String getRedirectUrl() {
       return "redirect:swagger-ui/";
    }
}`,
};

const tableOfContents = [
  ["overview", "1. Overview"],
  ["springdoc", "2. Changing Swagger UI URL Prefix With Springdoc"],
  ["properties", "2.1. Using the application.properties File"],
  ["configuration", "2.2. Using Configuration Class"],
  ["springfox", "3. Changing Swagger UI URL Prefix With Springfox"],
  ["springfox-properties", "3.1. Using the application.properties File"],
  ["docket", "3.2. Using Docket Bean in Configuration"],
  ["redirect", "4. Adding a Redirect Controller"],
  ["conclusion", "5. Conclusion"],
];

async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    // Clipboard access can be unavailable in local previews.
    return false;
  }
}

function BaeldungLogo() {
  return (
    <a className="baeldung-logo" href="/api/docs" aria-label="Baeldung home">
      <span className="baeldung-mark" aria-hidden="true">
        B
      </span>
      <span className="baeldung-word">baeldung</span>
    </a>
  );
}

function CodeBlock({
  children,
  label = "Java",
}: {
  children: string;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    if (await copyText(children)) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  }

  return (
    <div className="article-code">
      <div className="code-toolbar">
        <span className="code-language">
          <Code2 size={14} />
          {label}
        </span>
        <button className="copy-code" type="button" onClick={copyCode}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>
        <code>{children}</code>
      </pre>
    </div>
  );
}

function NavMenu({
  label,
  items,
}: {
  label: string;
  items: string[];
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="nav-menu">
      <button
        className="nav-menu-trigger"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {label}
        <ChevronDown size={15} className={open ? "rotate-180" : ""} />
      </button>
      {open ? (
        <div className="nav-menu-popover">
          {items.map((item) => (
            <a href="#article" key={item} onClick={() => setOpen(false)}>
              {item}
              <ArrowRight size={13} />
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ArticleSection({
  id,
  title,
  children,
  level = 2,
}: {
  id: string;
  title: string;
  children: ReactNode;
  level?: 2 | 3;
}) {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <section id={id} className={`article-section level-${level}`}>
      <Heading>{title}</Heading>
      {children}
    </section>
  );
}

function useOpenApiDocument(openapiUrl: string) {
  const [doc, setDoc] = useState<OpenApiDocument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(openapiUrl, {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          throw new Error(`${openapiUrl} responded ${response.status}`);
        }
        const nextDoc = (await response.json()) as OpenApiDocument;
        if (!cancelled) setDoc(nextDoc);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load the OpenAPI document",
          );
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [openapiUrl]);

  return { doc, error };
}

function DocsHeader({
  active,
  title,
  openapiUrl,
}: {
  active: "swagger" | "redoc";
  title: string;
  openapiUrl: string;
}) {
  return (
    <header className="docs-header">
      <div className="site-container docs-header-inner">
        <BaeldungLogo />
        <span className="docs-header-title">{title}</span>
        <nav className="docs-surface-nav" aria-label="API documentation">
          <a className={active === "swagger" ? "active" : ""} href="/api/swagger">
            Swagger UI
          </a>
          <a className={active === "redoc" ? "active" : ""} href="/api/redoc">
            ReDoc
          </a>
          <a href="/api/docs">Article</a>
        </nav>
        <a className="docs-openapi-link" href={openapiUrl}>
          OpenAPI JSON <ArrowRight size={14} />
        </a>
      </div>
    </header>
  );
}

function MethodBadge({ method }: { method: Endpoint["method"] }) {
  return <span className={`method-badge method-${method.toLowerCase()}`}>{method}</span>;
}

function ApiLoadingState({ error }: { error: string | null }) {
  return (
    <div className="api-loading">
      <div className="api-loading-mark">{error ? "!" : "…"}</div>
      <h2>{error ? "OpenAPI document unavailable" : "Loading API reference"}</h2>
      <p>{error ?? "Fetching the latest routes and schemas from your application."}</p>
    </div>
  );
}

function SwaggerSurface({ openapiUrl, title }: { openapiUrl: string; title: string }) {
  const studio = useStudio(openapiUrl);
  const { doc, loadError: error } = studio;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const endpoints = studio.endpoints;
  const groups = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return groupByTag(endpoints)
      .map(([tag, items]) => [
        tag,
        items.filter(
          (item) =>
            !query ||
            `${item.method} ${item.path} ${item.summary}`.toLowerCase().includes(query),
        ),
      ] as [string, Endpoint[]])
      .filter(([, items]) => items.length > 0);
  }, [endpoints, filter]);
  const selected = endpoints.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="api-surface">
      <DocsHeader active="swagger" title="Swagger UI" openapiUrl={openapiUrl} />
      <div className="site-container api-surface-body">
        <div className="api-surface-intro">
          <div>
            <p className="api-eyebrow">Interactive API documentation</p>
            <h1>{doc?.info?.title ?? title}</h1>
            <p>Explore endpoints, inspect parameters, and keep your integration moving.</p>
          </div>
          <div className="api-version">{doc?.info?.version ? `v${doc.info.version}` : "OpenAPI 3"}</div>
        </div>
        {studio.loading || !doc ? <ApiLoadingState error={error} /> : (
          <div className="swagger-layout">
            <aside className="swagger-sidebar">
              <label className="api-search">
                <Search size={15} />
                <input
                  type="search"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                  placeholder="Filter endpoints"
                  aria-label="Filter endpoints"
                />
              </label>
              {groups.map(([tag, items]) => (
                <div className="swagger-group" key={tag}>
                  <p>{tag}</p>
                  {items.map((endpoint) => (
                    <button
                      className={selectedId === endpoint.id ? "selected" : ""}
                      type="button"
                      key={endpoint.id}
                      onClick={() => {
                        setSelectedId(endpoint.id);
                        studio.selectEndpoint(endpoint.id);
                      }}
                    >
                      <MethodBadge method={endpoint.method} />
                      <span>{endpoint.path}</span>
                    </button>
                  ))}
                </div>
              ))}
            </aside>
            <main className="swagger-main">
              {selected ? (
                <EndpointDetail
                  endpoint={selected}
                  doc={doc}
                  openapiUrl={openapiUrl}
                  onTryItOut={() => {
                    if (studio.missingRequired.length === 0) void studio.send();
                  }}
                  sending={studio.sending}
                  response={studio.response?.body ?? null}
                  hasResponse={Boolean(studio.response)}
                  studio={studio}
                  canTry={studio.missingRequired.length === 0}
                />
              ) : (
                <div className="api-empty">
                  <Code2 size={25} />
                  <h2>Select an endpoint</h2>
                  <p>Choose a route from the left to inspect its contract.</p>
                </div>
              )}
            </main>
          </div>
        )}
      </div>
    </div>
  );
}

function EndpointDetail({
  endpoint,
  doc,
  openapiUrl,
  onTryItOut,
  sending,
  response,
  hasResponse,
  studio,
  canTry,
}: {
  endpoint: Endpoint;
  doc: OpenApiDocument;
  openapiUrl: string;
  onTryItOut: () => void;
  sending: boolean;
  response: string | null;
  hasResponse: boolean;
  studio: StudioApi;
  canTry: boolean;
}) {
  return (
    <article className="endpoint-detail">
      <div className="endpoint-heading">
        <MethodBadge method={endpoint.method} />
        <code>{endpoint.path}</code>
      </div>
      <h2>{endpoint.summary || "Untitled operation"}</h2>
      {endpoint.description ? <p>{endpoint.description}</p> : null}
      <div className="endpoint-actions">
        <button
          className="api-primary-button"
          type="button"
          onClick={onTryItOut}
          disabled={sending || !canTry}
          title={canTry ? "Send this request" : "Fill required parameters first"}
        >
          {sending ? "Sending…" : "Try it out"} <ArrowRight size={14} />
        </button>
        <a className="api-secondary-button" href={openapiUrl}>
          View schema
        </a>
      </div>
      {hasResponse && response !== null ? (
        <div className="try-response">
          <div>
            <span>Latest response</span>
            <button
              type="button"
              onClick={() => void copyText(response)}
            >
              Copy
            </button>
          </div>
          <pre>{response}</pre>
        </div>
      ) : null}
      <div className="swagger-request-console">
        <div className="request-console-label">Request builder</div>
        <AuthCard auth={studio.auth} onChange={studio.setAuth} />
        <RequestBar
          method={studio.method}
          onMethodChange={studio.setMethod}
          url={studio.url}
          onUrlChange={studio.updateUrl}
          onResetUrl={studio.resetUrlToSpec}
          urlIsCustom={studio.urlIsCustom}
          sending={studio.sending}
          disabled={studio.loading || studio.missingRequired.length > 0}
          onSend={() => void studio.send()}
          curlCommand={studio.curlCommand}
        />
        <RequestPanel studio={studio} />
      </div>
      {endpoint.params.length > 0 ? (
        <section className="endpoint-block">
          <h3>Parameters</h3>
          <div className="parameter-list">
            {endpoint.params.map((param) => (
              <div className="parameter-row" key={`${param.in}-${param.name}`}>
                <div>
                  <code>{param.name}</code>
                  <span>{param.in}{param.required ? " · required" : ""}</span>
                </div>
                <strong>{schemaTypeLabel(param.schema, doc) || "any"}</strong>
                <p>{param.description || "No description provided."}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <section className="endpoint-block">
        <h3>Responses</h3>
        <div className="response-list">
          {Object.entries(endpoint.responses).map(([status, response]) => (
            <div className="response-row" key={status}>
              <strong>{status}</strong>
              <span>{response.description || "Successful response"}</span>
            </div>
          ))}
        </div>
      </section>
    </article>
  );
}

function ReDocSurface({ openapiUrl, title }: { openapiUrl: string; title: string }) {
  const { doc, error } = useOpenApiDocument(openapiUrl);
  const endpoints = useMemo(() => (doc ? parseEndpoints(doc) : []), [doc]);
  const groups = useMemo(() => {
    const seen = new Set<string>();
    return groupByTag(endpoints)
      .map(([tag, items]) => [
        tag,
        items.filter((item) => {
          if (seen.has(item.id)) return false;
          seen.add(item.id);
          return true;
        }),
      ] as [string, Endpoint[]])
      .filter(([, items]) => items.length > 0);
  }, [endpoints]);

  return (
    <div className="api-surface redoc-surface">
      <DocsHeader active="redoc" title="ReDoc" openapiUrl={openapiUrl} />
      {!doc ? <ApiLoadingState error={error} /> : (
        <div className="site-container redoc-layout">
          <aside className="redoc-sidebar">
            <div className="redoc-brand">
              <p className="api-eyebrow">Reference</p>
              <h1>{doc.info?.title ?? title}</h1>
              <span>{doc.info?.version ? `Version ${doc.info.version}` : "OpenAPI 3"}</span>
            </div>
            <p className="redoc-nav-label">Contents</p>
            {groups.map(([tag, items]) => (
              <div className="redoc-nav-group" key={tag}>
                <a href={`#redoc-${tag}`}>{tag}</a>
                {items.map((endpoint) => (
                  <a className="redoc-nav-endpoint" href={`#${endpointAnchor(endpoint)}`} key={endpoint.id}>
                    {endpoint.method} {endpoint.path}
                  </a>
                ))}
              </div>
            ))}
          </aside>
          <main className="redoc-main">
            <div className="redoc-hero">
              <p className="api-eyebrow">API reference</p>
              <h1>{doc.info?.title ?? title}</h1>
              <p>{doc.info?.description || "A clear, complete reference for the API surface."}</p>
            </div>
            {groups.map(([tag, items]) => (
              <section className="redoc-group" id={`redoc-${tag}`} key={tag}>
                <h2>{tag}</h2>
                {items.map((endpoint) => (
                  <div className="redoc-operation" id={endpointAnchor(endpoint)} key={endpoint.id}>
                    <div className="redoc-operation-heading">
                      <MethodBadge method={endpoint.method} />
                      <code>{endpoint.path}</code>
                    </div>
                    <h3>{endpoint.summary || "Untitled operation"}</h3>
                    {endpoint.description ? <p>{endpoint.description}</p> : null}
                    <div className="redoc-contract">
                      <div>
                        <span>Responses</span>
                        {Object.entries(endpoint.responses).map(([status, response]) => (
                          <p key={status}><strong>{status}</strong> {response.description || "Successful response"}</p>
                        ))}
                      </div>
                      <pre><code>{`curl -X ${endpoint.method} "${endpoint.path}"`}</code></pre>
                    </div>
                  </div>
                ))}
              </section>
            ))}
          </main>
        </div>
      )}
    </div>
  );
}

function endpointAnchor(endpoint: Endpoint) {
  const codePoints = [...endpoint.id]
    .map((character) => character.codePointAt(0)!.toString(16).padStart(4, "0"))
    .join("");
  return `operation-${codePoints}`;
}

export default function App() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [config] = useState(() => document.body.dataset);
  const surface = config.surface;

  async function copyArticleLink() {
    if (await copyText(window.location.href)) {
      setLinkCopied(true);
      window.setTimeout(() => setLinkCopied(false), 1600);
    }
  }

  useEffect(() => {
    document.title =
      surface === "swagger"
        ? "Swagger UI · Baeldung"
        : surface === "redoc"
          ? "ReDoc · Baeldung"
          : "Change Swagger-UI URL prefix · Baeldung";
  }, [surface]);

  if (surface === "swagger") {
    return <SwaggerSurface openapiUrl={config.openapi || "/api/openapi.json"} title={config.title || "API"} />;
  }

  if (surface === "redoc") {
    return <ReDocSurface openapiUrl={config.openapi || "/api/openapi.json"} title={config.title || "API"} />;
  }

  return (
    <div className="baeldung-app">
      <div className="top-strip">
        <div className="site-container top-strip-inner">
          <span>Baeldung</span>
          <span>Learn Java, Spring, and more</span>
        </div>
      </div>

      <header className="site-header">
        <div className="site-container site-header-inner">
          <BaeldungLogo />
          <button
            className="mobile-menu-button"
            type="button"
            aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileNavOpen}
            aria-controls="primary-navigation"
            onClick={() => setMobileNavOpen((value) => !value)}
          >
            {mobileNavOpen ? <X /> : <Menu />}
          </button>
          <nav
            id="primary-navigation"
            className={`primary-nav ${mobileNavOpen ? "is-open" : ""}`}
            aria-label="Primary navigation"
          >
            <a href="#article" onClick={() => setMobileNavOpen(false)}>
              Start Here
            </a>
            <NavMenu label="Spring Courses" items={["Spring Boot", "Spring Security", "Spring AI"]} />
            <NavMenu label="Java Courses" items={["Java Core", "Java Collections", "Java Testing"]} />
            <a href="#pricing" onClick={() => setMobileNavOpen(false)}>
              Pricing
            </a>
            <NavMenu label="About" items={["About Baeldung", "The Full Archive", "Contact"]} />
          </nav>
          <div className="header-actions">
            <a className="search-button" href="#overview" aria-label="Jump to article">
              <Search size={17} />
              <span>Read</span>
            </a>
            <a className="login-link" href="#login">
              Log in
            </a>
            <a className="header-cta" href="#courses">
              Explore courses
            </a>
          </div>
        </div>
      </header>

      <div className="article-shell site-container" id="article">
        <div className="breadcrumbs">
          <a href="/api/docs">Home</a>
          <span>/</span>
          <a href="#spring-boot">Spring Boot</a>
          <span>/</span>
          <span>OpenAPI &amp; Swagger</span>
        </div>

        <div className="article-layout">
          <aside className="article-sidebar" aria-label="Article navigation">
            <div className="sidebar-card">
              <p className="sidebar-label">In this article</p>
              <nav>
                {tableOfContents.map(([id, label]) => (
                  <a href={`#${id}`} key={id}>
                    {label}
                  </a>
                ))}
              </nav>
            </div>
            <div className="sidebar-note">
              <span className="note-icon">✦</span>
              <strong>Level up your Spring skills</strong>
              <p>Build production-ready applications with Baeldung courses.</p>
              <a href="#courses">
                View courses <ArrowRight size={14} />
              </a>
            </div>
          </aside>

          <main className="article-content">
            <header className="article-header">
              <div className="article-kicker">
                <span>Spring Boot</span>
                <span>OpenAPI &amp; Swagger</span>
              </div>
              <h1>Change Swagger-UI URL prefix</h1>
              <p className="article-deck">
                Learn how to customize the Swagger UI URL when using Springdoc
                or Springfox in a Spring Boot application.
              </p>
              <div className="article-meta">
                <span>
                  <Clock3 size={15} /> Last updated: May 11, 2024
                </span>
                <span className="meta-divider" />
                <span>
                  Written by: <a href="#author">Sudarshan Hiray</a>
                </span>
                <span className="meta-divider" />
                <span>
                  Reviewed by: <a href="#reviewer">Luis Javier Peris</a>
                </span>
              </div>
            </header>

            <div className="article-body">
              <ArticleSection id="overview" title="1. Overview">
                <p>
                  As good developers, we know that documentation is essential
                  to building REST APIs, as it helps consumers of the APIs work
                  seamlessly. Most Java developers today are working with
                  Spring Boot. As of today, two tools simplify the generation
                  and maintenance of Swagger API docs using Springfox and
                  SpringDoc.
                </p>
                <p>
                  In this tutorial, we&apos;ll discuss how to change the
                  Swagger-UI URL prefix that&apos;s provided by these tools by
                  default.
                </p>
              </ArticleSection>

              <ArticleSection
                id="springdoc"
                title="2. Changing Swagger UI URL Prefix With Springdoc"
              >
                <p>
                  To begin, we can check out how to set up the REST API
                  documentation using OpenAPI 3.0.
                </p>
                <p>
                  First, as per the above article, we&apos;ll need to add an
                  entry to add the dependency for SpringDoc:
                </p>
                <CodeBlock>{codeSamples.dependency}</CodeBlock>
                <div className="callout">
                  <strong>Tip</strong>
                  <span>
                    The default URL for the Swagger UI is{" "}
                    <code>http://localhost:8080/swagger-ui.html</code>.
                  </span>
                </div>
                <p>
                  Now let&apos;s look at two approaches to customize the
                  Swagger-UI URL. We&apos;ll begin with <code>/myproject</code>.
                </p>
              </ArticleSection>

              <ArticleSection id="properties" title="2.1. Using the application.properties File" level={3}>
                <p>
                  As we&apos;re already familiar with the many different
                  properties in Spring, we&apos;ll need to add the following
                  properties to the <code>application.properties</code> file:
                </p>
                <CodeBlock label="Properties">{codeSamples.properties}</CodeBlock>
              </ArticleSection>

              <ArticleSection id="configuration" title="2.2. Using Configuration Class" level={3}>
                <p>We can also make this change in the configuration file:</p>
                <CodeBlock>{codeSamples.configuration}</CodeBlock>
                <p>
                  In this case, we&apos;ll need to register the listener before
                  the application starts:
                </p>
                <CodeBlock>{codeSamples.listener}</CodeBlock>
              </ArticleSection>

              <ArticleSection
                id="springfox"
                title="3. Changing Swagger UI URL Prefix With Springfox"
              >
                <p>
                  We can look at how to set up the REST API documentation by
                  setting an example and description with Swagger and setting
                  up Swagger 2 with a Spring REST API using Springfox.
                </p>
                <p>
                  First, as per the above articles, we&apos;ll need to add an
                  entry to add the dependency for Springfox:
                </p>
                <CodeBlock>{codeSamples.springfoxDependency}</CodeBlock>
                <p>
                  Now let&apos;s say we want to change this URL to{" "}
                  <code>http://localhost:8080/myproject/swagger-ui/index.html</code>.
                  Let&apos;s review two approaches that can help us achieve it.
                </p>
              </ArticleSection>

              <ArticleSection id="springfox-properties" title="3.1. Using the application.properties File" level={3}>
                <p>
                  Similar to the above example for SpringDoc, adding the
                  following property in the <code>application.properties</code>{" "}
                  file will help us change it successfully:
                </p>
                <CodeBlock label="Properties">
                  {"springfox.documentation.swagger-ui.base-url=myproject"}
                </CodeBlock>
              </ArticleSection>

              <ArticleSection id="docket" title="3.2. Using Docket Bean in Configuration" level={3}>
                <CodeBlock>{codeSamples.docket}</CodeBlock>
              </ArticleSection>

              <ArticleSection id="redirect" title="4. Adding a Redirect Controller">
                <p>
                  We can also add a redirection logic to the API endpoint. In
                  this case, it won&apos;t matter if we use SpringDoc or
                  Springfox:
                </p>
                <CodeBlock>{codeSamples.redirect}</CodeBlock>
              </ArticleSection>

              <ArticleSection id="conclusion" title="5. Conclusion">
                <p>
                  In this article, we learned how to change the default
                  Swagger-UI URL for REST API documentation using Springfox and
                  SpringDoc.
                </p>
                <div className="pro-cta" id="courses">
                  <div>
                    <span className="pro-eyebrow">Baeldung Pro</span>
                    <h3>Keep learning with hands-on projects</h3>
                    <p>
                      The code backing this article is available on GitHub.
                      Start learning and coding on the project.
                    </p>
                  </div>
                  <a href="#courses">
                    Explore Baeldung Pro <ArrowRight size={16} />
                  </a>
                </div>
              </ArticleSection>
            </div>
          </main>

          <aside className="article-right-rail" aria-label="Article resources">
            <div className="rail-card">
              <p className="rail-label">Try it yourself</p>
              <h2>Explore the live API docs</h2>
              <p>Open the generated OpenAPI schema in an interactive console.</p>
              <a className="rail-button" href="/api/swagger">
                Open Swagger UI <ArrowRight size={15} />
              </a>
              <a className="rail-secondary-link" href={config.openapi || "/api/openapi.json"}>
                View OpenAPI JSON
              </a>
            </div>
            <div className="share-card">
              <p className="rail-label">Share this article</p>
              <div className="share-icons">
                <button
                  type="button"
                  aria-label="Copy article link"
                  title="Copy article link"
                  onClick={() => void copyArticleLink()}
                >
                  {linkCopied ? <Check size={16} /> : <Copy size={16} />}
                </button>
              </div>
            </div>
          </aside>
        </div>
      </div>

      <footer className="site-footer" id="pricing">
        <div className="site-container footer-inner">
          <BaeldungLogo />
          <p>Programming tutorials for developers who build things.</p>
          <div className="footer-links">
            <a href="#courses">Courses</a>
            <a href="#article">The Full Archive</a>
            <a href="#article">About</a>
            <a href="#article">Privacy</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
