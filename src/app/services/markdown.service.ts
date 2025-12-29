// src/app/services/markdown.service.ts
import { Injectable } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { marked } from 'marked';

@Injectable({
    providedIn: 'root'
})
export class MarkdownService {
    constructor(private sanitizer: DomSanitizer) {
        // Configure marked options for security and formatting
        marked.setOptions({
            gfm: true, // GitHub Flavored Markdown
            breaks: true, // Convert \n to <br>
        });
    }

    /**
     * Parse markdown text to HTML with copy/download buttons on code blocks and tables
     * @param markdown - Raw markdown string
     * @returns Sanitized HTML ready for rendering
     */
    parse(markdown: string): SafeHtml {
        if (!markdown) return '';

        // Parse markdown to HTML
        let html = marked.parse(markdown, { async: false }) as string;

        // Wrap code blocks and tables with action buttons
        html = this.wrapCodeBlocks(html);
        html = this.wrapTables(html);

        // Sanitize and return
        return this.sanitizer.bypassSecurityTrustHtml(html);
    }

    /**
     * Parse markdown inline (for single-line content without block elements)
     * @param markdown - Raw markdown string
     * @returns Sanitized HTML ready for rendering
     */
    parseInline(markdown: string): SafeHtml {
        if (!markdown) return '';

        const html = marked.parseInline(markdown, { async: false }) as string;
        return this.sanitizer.bypassSecurityTrustHtml(html);
    }

    /**
     * Wrap <pre><code> blocks with a container that includes copy/download buttons
     */
    private wrapCodeBlocks(html: string): string {
        // Match <pre><code> blocks (with optional class for language)
        const preCodeRegex = /<pre><code(?: class="language-(\w+)")?>([\s\S]*?)<\/code><\/pre>/g;

        return html.replace(preCodeRegex, (match, language, code) => {
            const lang = language || 'text';
            const escapedCode = this.escapeHtmlAttribute(code);
            return `
                <div class="code-wrapper" data-language="${lang}">
                    <div class="copy-download-buttons">
                        <button type="button" class="action-icon-btn copy-code-btn" data-code="${escapedCode}" title="Copy code">
                            <span class="material-icons">content_copy</span>
                        </button>
                        <button type="button" class="action-icon-btn download-code-btn" data-code="${escapedCode}" data-lang="${lang}" title="Download">
                            <span class="material-icons">download</span>
                        </button>
                    </div>
                    <pre><code${language ? ` class="language-${language}"` : ''}>${code}</code></pre>
                </div>
            `.trim();
        });
    }

    /**
     * Wrap <table> elements with a container that includes copy/download buttons
     */
    private wrapTables(html: string): string {
        // Match table elements
        const tableRegex = /<table>([\s\S]*?)<\/table>/g;

        return html.replace(tableRegex, (match, tableContent) => {
            return `
                <div class="table-wrapper">
                    <div class="copy-download-buttons">
                        <button type="button" class="action-icon-btn copy-table-btn" title="Copy as CSV">
                            <span class="material-icons">content_copy</span>
                        </button>
                        <button type="button" class="action-icon-btn download-table-btn" title="Download CSV">
                            <span class="material-icons">download</span>
                        </button>
                    </div>
                    <table>${tableContent}</table>
                </div>
            `.trim();
        });
    }

    /**
     * Escape HTML content for use in data attributes
     */
    private escapeHtmlAttribute(str: string): string {
        return str
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
}
