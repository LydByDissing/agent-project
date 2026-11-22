// [origin ref=llm-dsl-gu1y.16 req=REQ-OPERATOR-EDU-011 c4=learn_app/learn_spa]
//   [intent]Link sanitiser for lesson Markdown and source URLs: only absolute http(s), fragments and single-slash relative paths survive.[/intent]
//   [inv]Protocol-relative (//host), backslash-host, javascript:, data: and mailto: hrefs always become '#'.[/inv]
// [/origin]
export const safeHref = (h: string): string => (/^(https?:\/\/|#|\/(?![/\\]))/i.test(h) ? h : '#');
