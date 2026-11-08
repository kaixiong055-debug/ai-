package com.youxuan.cms;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.util.HtmlUtils;
import java.net.URI;
import java.time.Instant;
import java.util.List;

@Controller
public class PublicController {
    private final GameService games;
    private final SeoService seo;
    private final CatalogService catalog;
    public PublicController(GameService games, SeoService seo,CatalogService catalog) { this.games = games; this.seo = seo;this.catalog=catalog; }

    @GetMapping("/favicon.ico")
    public ResponseEntity<Void> favicon() {
        return ResponseEntity.status(HttpStatus.FOUND).location(URI.create("/site/favicon.svg")).build();
    }

    @GetMapping("/")
    public String home(@RequestParam(defaultValue = "") String q,@RequestParam(defaultValue="")String category,@RequestParam(defaultValue="recommended")String sort,@RequestParam(defaultValue="1")int page, Model model) {
        q = q.trim(); if (q.length() > 120) q = q.substring(0, 120);
        SiteSettings settings = games.settings();
        model.addAttribute("settings", settings);
        var result=catalog.page(q,"published",category,sort,page,18);
        var metadata=new java.util.HashMap<>(seo.home(settings, !q.isBlank()||!category.isBlank()||!sort.equals("recommended")));
        if(result.page()>1){metadata.put("title",metadata.get("title")+" · 第"+result.page()+"页");if(!metadata.get("canonical").isBlank())metadata.put("canonical",metadata.get("canonical")+"?page="+result.page());}
        model.addAttribute("seo",metadata);
        model.addAttribute("games",result.items());model.addAttribute("pager",result);
        model.addAttribute("category",category);model.addAttribute("sort",sort);model.addAttribute("categories",catalog.categories(true));
        model.addAttribute("pageNumbers",java.util.stream.IntStream.rangeClosed(Math.max(1,result.page()-2),Math.min(result.pages(),result.page()+2)).boxed().toList());
        model.addAttribute("q", q);
        model.addAttribute("featured",q.isBlank()&&category.isBlank()&&result.page()==1&&sort.equals("recommended")?catalog.featured():null);
        return "site-home";
    }

    @GetMapping("/games/{slug}")
    public ResponseEntity<Void> trailingSlash(@PathVariable String slug) {
        Game game = games.publishedBySlug(slug).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        return ResponseEntity.status(HttpStatus.MOVED_PERMANENTLY).location(URI.create("/games/" + game.slug + "/")).build();
    }

    @GetMapping("/games/{slug}/")
    public String game(@PathVariable String slug, Model model, HttpServletResponse response) {
        var found = games.publishedBySlug(slug);
        if (found.isEmpty()) { response.setStatus(404); return missing(model, response); }
        return render(found.get(), false, model, response);
    }

    @GetMapping("/admin/preview/{id}")
    public String preview(@PathVariable String id, Model model, HttpServletResponse response) {
        var found = games.find(id);
        if (found.isEmpty()) { response.setStatus(404); return missing(model, response); }
        response.setHeader("Cache-Control", "no-store");
        return render(found.get(), true, model, response);
    }

    private String render(Game game, boolean preview, Model model, HttpServletResponse response) {
        SiteSettings settings = games.settings();
        var metadata = seo.game(game, settings, preview);
        if (metadata.get("robots").startsWith("noindex")) response.setHeader("X-Robots-Tag", "noindex, follow");
        model.addAttribute("game", game); model.addAttribute("settings", settings);
        model.addAttribute("seo", metadata); model.addAttribute("preview", preview);
        return "site-game";
    }

    private String missing(Model model, HttpServletResponse response) {
        model.addAttribute("settings", games.settings());
        response.setHeader("X-Robots-Tag", "noindex");
        return "error/404";
    }

    @GetMapping(value = "/robots.txt", produces = "text/plain;charset=UTF-8")
    @ResponseBody
    public String robots() {
        SiteSettings settings = games.settings();
        if (!seo.indexable(settings)) return "User-agent: *\nDisallow: /\n";
        return "User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nDisallow: /login\nDisallow: /logout\n"
            + "Sitemap: " + seo.origin(settings) + "/sitemap.xml\n";
    }

    @GetMapping(value = "/sitemap.xml", produces = "application/xml;charset=UTF-8")
    @ResponseBody
    public String sitemap(HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        SiteSettings settings = games.settings();
        StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<?xml-stylesheet type=\"text/xsl\" href=\"/site/sitemap.xsl\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n");
        if (seo.indexable(settings)) {
            String base = seo.origin(settings);
            appendUrl(xml, base + "/", "");
            for (var row : catalog.sitemap()) appendUrl(xml, base + "/games/" + row.get("slug") + "/", String.valueOf(row.get("updated_at")));
        }
        return xml.append("</urlset>\n").toString();
    }

    private static void appendUrl(StringBuilder out, String url, String updated) {
        out.append("  <url>\n    <loc>").append(HtmlUtils.htmlEscape(url)).append("</loc>\n");
        if (updated != null && !updated.isBlank()) {
            try { out.append("    <lastmod>").append(Instant.parse(updated).truncatedTo(java.time.temporal.ChronoUnit.SECONDS)).append("</lastmod>\n"); }
            catch (RuntimeException ignored) { /* Old imports may not have an ISO timestamp. */ }
        }
        out.append("  </url>\n");
    }
}
