import json

from integrations.openai_client import get_openai_client, get_openai_deployment


def generate_summary(products: list, criteria: dict, recommendation: dict) -> str:
    """
    Uses Azure OpenAI to generate a short business summary
    of the search results and recommendation.
    """
    if not products:
        return "No products found matching your criteria."

    try:
        client = get_openai_client()
        deployment = get_openai_deployment()

        top5 = products[:5]
        product_lines = "\n".join(
            [
                f"- {product['name'][:60]} | ${product.get('price', 'N/A')} | "
                f"{product.get('condition', 'N/A')} | {product.get('site', 'N/A')}"
                for product in top5
            ]
        )

        rec_line = (
            f"{recommendation['name'][:60]} at ${recommendation.get('price', 'N/A')}"
            if recommendation
            else "None"
        )

        prompt = f"""You are IGNA, an AI research agent. Write a short 2-3 sentence
business summary of these product search results. Be specific about prices and value.

Search criteria: {json.dumps(criteria)}
Top results:
{product_lines}
Top recommendation: {rec_line}

Write the summary now:"""

        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )

        return response.choices[0].message.content.strip()

    except Exception as exc:
        print(f"   [IGNA Brain] Summary generation failed: {exc}")
        if recommendation:
            return (
                f"Found {len(products)} products matching your criteria. "
                f"Top recommendation: {recommendation.get('name', 'N/A')[:60]} "
                f"at ${recommendation.get('price', 'N/A')} "
                f"from {recommendation.get('site', 'N/A')}."
            )
        return f"Found {len(products)} products matching your criteria."
