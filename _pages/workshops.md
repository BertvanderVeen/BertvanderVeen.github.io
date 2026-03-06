---
layout: default
title: Past workshops
permalink: /workshops/
nav: true
nav_order: 3
---

{% assign workshop_items = site.workshops | sort: 'date' | reverse %}

{% for item in workshop_items %}
  <h3>{{ item.title }}</h3>
  <p>{{ item.content }}</p>
{% endfor %}

{% if item.category == 'workshop' %}
  <span class="badge">{{ item.category }}</span>
{% endif %}