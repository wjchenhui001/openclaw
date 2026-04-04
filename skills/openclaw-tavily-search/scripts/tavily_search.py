#!/usr/bin/env python3
"""
Tavily Search Skill
Search the web using Tavily AI API.
"""
import os
import sys
import json
import argparse
import requests
from pathlib import Path

def load_api_key():
    """Load TAVILY_API_KEY from environment or ~/.openclaw/.env"""
    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        env_path = Path.home() / '.openclaw' / '.env'
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith('TAVILY_API_KEY='):
                        api_key = line.strip().split('=', 1)[1]
                        break
    if not api_key:
        raise ValueError("TAVILY_API_KEY not found in environment or ~/.openclaw/.env")
    return api_key

def search_tavily(query, max_results=5, include_answer=False, format='raw'):
    """Perform Tavily search and return results."""
    api_key = load_api_key()
    url = 'https://api.tavily.com/search'
    payload = {
        'api_key': api_key,
        'query': query,
        'max_results': max_results,
        'include_answer': include_answer
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # Format output based on requested format
    if format == 'brave':
        # Brave-compatible schema: {query, results:[{title,url,snippet}], answer?}
        output = {
            'query': query,
            'results': [
                {'title': r.get('title'), 'url': r.get('url'), 'snippet': r.get('content', '')}
                for r in data.get('results', [])
            ]
        }
        if include_answer and data.get('answer'):
            output['answer'] = data['answer']
        return output
    elif format == 'md':
        # Markdown list
        lines = [f"# Tavily Search: {query}\n"]
        if include_answer and data.get('answer'):
            lines.append(f"**Answer:** {data['answer']}\n")
        for r in data.get('results', []):
            lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content', '')[:200]}...")
        return '\n'.join(lines)
    else:
        # Raw JSON (default)
        return data

def main():
    parser = argparse.ArgumentParser(description='Tavily web search')
    parser.add_argument('--query', required=True, help='Search query')
    parser.add_argument('--max-results', type=int, default=5, help='Max results (default 5)')
    parser.add_argument('--include-answer', action='store_true', help='Include AI answer if available')
    parser.add_argument('--format', choices=['raw', 'brave', 'md'], default='raw', help='Output format')
    args = parser.parse_args()

    try:
        result = search_tavily(args.query, args.max_results, args.include_answer, args.format)
        if isinstance(result, str):
            print(result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
