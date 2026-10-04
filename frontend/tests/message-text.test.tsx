import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MessageText } from '../src/App';

describe('Telegram message text links', () => {
  it('shows hidden URLs on their original labels, including after an emoji', () => {
    const text = '😀 삼성전자 상세보기\nSK하이닉스 상세보기';
    const first = text.indexOf('상세보기');
    const second = text.lastIndexOf('상세보기');
    const html = renderToStaticMarkup(<MessageText text={text} links={['https://example.com/samsung', 'https://example.com/sk']} textLinks={[
      { offset: first, length: 4, url: 'https://example.com/samsung' },
      { offset: second, length: 4, url: 'https://example.com/sk' },
    ]} />);

    expect(html.match(/class="embedded-link"/g)).toHaveLength(2);
    expect(html).toContain('href="https://example.com/samsung"');
    expect(html).toContain('href="https://example.com/sk"');
    expect(html.match(/>상세보기<\/a>/g)).toHaveLength(2);
    expect(html).not.toContain('>https://example.com/samsung</a>');
  });

  it('does not invent a link for plain text or an unsafe target', () => {
    const plain = renderToStaticMarkup(<MessageText text="상세보기" links={[]} />);
    const unsafe = renderToStaticMarkup(<MessageText text="상세보기" links={[]} textLinks={[{ offset: 0, length: 4, url: 'javascript:alert(1)' }]} />);
    expect(plain).not.toContain('<a');
    expect(unsafe).not.toContain('<a');
  });
});
