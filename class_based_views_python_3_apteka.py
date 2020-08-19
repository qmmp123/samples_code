class CommonMixIn:

    def get_discounts(self):
        return Discounts.objects.filter(pub_date__lte=timezone.localdate(), end_date__gte=timezone.localdate())

    def get_articles(self):
        return Article.objects.all()

    def get_pharmacies(self):
        return Pharmacy.objects.all()

    # Mixin для получения общей информации(корзина, заголовок страницы) во всех views
    def get_common_info(self) -> Dict[str, str]:
        context = {}
        if not self.request.session.get("cart"):
            cart = Cart()
            self.request.session["cart"] = cart.items_list()
        self.request.session["forgot"] = False
        cart = Cart(self.request.session.get("cart"))
        context["cart"] = cart.to_dict()
        context["title"] = self.title
        context["pharms"] = self.get_pharmacies()
        context["current_year"] = timezone.now().date().year
        try:
            context["user"] = self.request.user
        except AttributeError:
            context["user"] = AnonymousUser
        return context


class CommonProductView(ListView, CommonMixIn):
    model = Product
    order_by = "cost"

    def get_queryset(self):
        products: querySetProductTypeHint = super().get_queryset()
        products = products.filter(Q(date=timezone.localdate()) | Q(mark=True), Q(show=True), Q(published=True)).exclude(cost=0)
        return products

    def get_context_data(self, **kwargs):
        context: dict = super(CommonProductView, self).get_context_data(**kwargs)
        context["page_url"] = "index"
        context.update(self.get_common_info())
        return context


class SimpleListView(ListView, CommonMixIn):

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_common_info())
        return context


class SimpleDetailView(DetailView, CommonMixIn):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_common_info())
        return context


class SearchProduct(CommonProductView):
    """
    Основной поиск
    Для начала ищется название товара у которого совпадает название сначала
    Затем добавляются товары, которых слова содержатся в назвнаии частями
    Если результатов нет, то такой же алгоритм но уже используется для МНН
    """
    title = "Результаты поиска"
    template_name = "search.html"
    paginate_by = 50
    context_object_name = "results"

    def get(self, request, *args, **kwargs):
        if request.GET.get("q") is None:
            return redirect("/")
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        products = super().get_queryset()
        products = products.prefetch_related('cost_category')
        self.query: str = self.request.GET.get("q").upper()
        results: List[Product] = list()
        results.extend(search_product_startswith(products, self.query))
        for product in search_product_contains(products, self.query):
            if product not in results:
                results.append(product)
        if len(results) == 0:
            results.extend(search_mnn_startswith(products, self.query))
            results.extend(search_mnn_contains(products, self.query))
            return results
        if len(results) > 50:
            results = results[:49]
        return list(results)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.GET.get("q") is None:
            return context
        if len(context.get("results")) == 0:
            context["query"] = self.request.GET.get("q")
            context["corrected_query"] = google_search_corrected_query(self.query)
        context["query"] = self.request.GET.get("q")
        return context


class SearchMnn(SearchProduct):
    """
    Поиск аналогов
    Ищется точное совпадение по МНН
    """

    def get(self, request, *args, **kwargs):
        return super(CommonProductView, self).get(request, *args, **kwargs)

    def get_queryset(self):
        products = super(CommonProductView, self).get_queryset()
        product = products.get(id=int(self.request.GET.get("obj_id")))
        products = sorted(
            products.filter(
                mnn=product.mnn
            ).exclude(
                id=product.id
            ).exclude(
                cost=0
            ).exclude(mnn='').exclude(mnn=None)[:50], key=lambda x: x.get_price_with_discount())
        return products


class ProductView(SimpleDetailView):
    """
    Страница товара
    """
    model = Product
    template_name = "product.html"
    context_object_name = "object"

    @property
    def title(self):
        return self.object.name


def autocomplete(req: HttpRequest):
    """
    Автодополнение
    """
    query = req.GET.get("q")
    if query is None or query == '':
        return HttpResponse('')
    products = Product.objects.filter(date=timezone.localdate(), show=True, published=True).order_by("cost").exclude(cost=0)
    sqs = products.filter(name__startswith=query.upper())[:15]
    suggestions = []
    ids = []
    for item in sqs:
        if item.id not in ids:
            ids.append(item.id)
            suggestions.append(item.to_dict(0, 0))
    if len(suggestions) < 5:
        sqs = products
        for item in req.GET.get("q").split(' '):
            sqs = sqs.filter(name__icontains=item.upper())
        for item in sqs:
            item: Product
            if item.id not in ids and len(suggestions) < 15:
                ids.append(item.id)
                suggestions.append(item.to_dict(0, 0))
    return JsonResponse(suggestions, safe=False)


def get_presence(req: HttpRequest):
    """
    Возвращает список аптек в которых есть этот товар
    """
    product: Product = Product.objects.get(id=int(req.GET.get("id")))
    pharms = Pharmacy.objects.filter(id__in=product.get_presence())
    return JsonResponse([pharm.to_dict() for pharm in pharms], safe=False)