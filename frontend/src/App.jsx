import { useState } from "react";

const API_BASE_URL = "http://127.0.0.1:8000";

function formatPrice(price) {
  if (price === null || price === undefined) {
    return "N/A";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(price);
}

export default function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          max_results_per_site: 8,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "Search request failed.");
      }

      const payload = await response.json();
      setResult(payload);
    } catch (submitError) {
      setError(submitError.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page-shell">
      <div className="hero-glow hero-glow-left" />
      <div className="hero-glow hero-glow-right" />

      <main className="layout">
        <section className="hero-card">
          <p className="eyebrow">AI Product Discovery</p>
          <h1>IGNA Competitive Product Research Agent</h1>
          <p className="hero-copy">
            Enter a product search query and let IGNA gather pricing, listings,
            and a recommendation across major storefronts.
          </p>

          <form className="search-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>What do you want to search?</span>
              <textarea
                rows="4"
                placeholder="Find smartphones under $500 with at least 6GB RAM"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                required
              />
            </label>

            <button className="submit-button" type="submit" disabled={loading}>
              {loading ? "Researching..." : "Search"}
            </button>
          </form>

          {error ? <div className="error-banner">{error}</div> : null}
        </section>

        <section className="results-panel">
          {!result && !loading ? (
            <div className="empty-state">
              <h2>Results will appear here</h2>
              <p>
                Run a search to see product matches, IGNA&apos;s recommendation,
                and the AI summary from the backend.
              </p>
            </div>
          ) : null}

          {loading ? (
            <div className="loading-card">
              <div className="spinner" />
              <p>IGNA is searching marketplaces and generating insights...</p>
            </div>
          ) : null}

          {result ? (
            <div className="results-stack">
              <div className="summary-grid">
                <article className="info-card">
                  <p className="card-label">Query</p>
                  <h2>{result.query}</h2>
                </article>

                <article className="info-card accent-card">
                  <p className="card-label">Total Found</p>
                  <h2>{result.total_found}</h2>
                </article>
              </div>

              {result.recommendation ? (
                <article className="recommendation-card">
                  <p className="card-label">Top Recommendation</p>
                  <h2>{result.recommendation.name}</h2>
                  <div className="recommendation-meta">
                    <span>{result.recommendation.site}</span>
                    <span>{formatPrice(result.recommendation.price)}</span>
                    <span>{result.recommendation.condition || "N/A"}</span>
                  </div>
                  {result.recommendation.url ? (
                    <a
                      href={result.recommendation.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open product link
                    </a>
                  ) : null}
                </article>
              ) : null}

              {result.summary ? (
                <article className="info-card">
                  <p className="card-label">AI Summary</p>
                  <p className="summary-copy">{result.summary}</p>
                </article>
              ) : null}

              <article className="info-card">
                <p className="card-label">Products</p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th>Site</th>
                        <th>Price</th>
                        <th>Condition</th>
                        <th>Rating</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.products.map((product) => (
                        <tr key={`${product.site}-${product.name}`}>
                          <td>
                            {product.url ? (
                              <a
                                className="product-link"
                                href={product.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {product.name}
                              </a>
                            ) : (
                              product.name
                            )}
                          </td>
                          <td>{product.site}</td>
                          <td>{formatPrice(product.price)}</td>
                          <td>{product.condition || "N/A"}</td>
                          <td>{product.rating ?? "N/A"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
