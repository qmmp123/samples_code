class WarningList(ListView):
    model = ProductWarning
    template_name = "exceptions.html"

    def get_queryset(self):
        warning_products = list(self.model.objects.filter(type_product="1"))
        danger_products = list(self.model.objects.filter(type_product="2"))
        # for k, v in itertools.zip_longest(warning_products, danger_products):
        #     print(k.name, v.name)
        return itertools.zip_longest(warning_products, danger_products)


class LoginView(FormView):
    template_name = 'login.html'
    form_class = LoginForm
    success_url = '/'

    def get(self, request: HttpRequest, *args, **kwargs):
        context = {}
        context.update(csrf(request))
        form = self.get_form_class()
        context["form"] = form
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, *args, **kwargs):
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request=request, user=user)
            if username == "director":
                return redirect("/director/")
            return redirect("/")
        else:
            return redirect("/login/")


class IndexView(ListView):
    form_class = OrderForm
    model = Order
    paginate_by = 50
    template_name = "index.html"
    context_object_name = "results"
    ordering = "-id"

    def get_queryset(self):
        list_orders = super().get_queryset()
        if not self.request.user.is_superuser:
            list_orders = list_orders.filter(creator=str(self.request.user))
        date_to = datetime.now().date()
        date_from = date_to - timedelta(days=21)
        list_orders = list_orders.filter(date__range=[date_from, date_to + timedelta(days=1)])
        list_orders = list_orders.exclude(status="7").exclude(status="8").order_by("-id")
        list_orders = list_orders.prefetch_related("product_set", "comment_set")
        return list_orders

    def get_context_data(self, **kwargs):
        if self.request.session.get("printing") is None:
            my_printing = []
            self.request.session["printing"] = my_printing
        context = super(IndexView, self).get_context_data(**kwargs)
        dateTo = datetime.now().date()
        dateFrom = dateTo - timedelta(days=21)
        paginator: Paginator = context.get("paginator")
        context["redir"] = "/?page="
        context["user"] = self.request.user
        context["users"] = User.objects.filter(is_superuser=False)
        context['nums'] = range(1, paginator.num_pages + 1)
        context['providers'] = Product.providers
        context["dateFrom"] = dateFrom.strftime("%d.%m.%Y")
        context["dateTo"] = dateTo.strftime("%d.%m.%Y")
        context['statuses'] = Order.statuses
        return context


class CreateOrder(CreateView):

    def post(self, request, *args, **kwargs):
        order = Order()
        order.purchaser = request.POST["purchaser"].lower()
        order.phone = request.POST["phone"]
        order.save()
        summary = 0
        for _, val in divisionRequest(request.POST).items():
            product = Product()
            product.order = order
            product.name = val["product"].lower()
            product.cost = convert_float(val["cost"])
            product.amount = val["amount"]
            summary += convert_float(val["cost"]) * convert_float(val["amount"])
            product.provider = val["prov"]
            if "ordered" in request.POST.keys():
                product.status = "2"
            product.custom_save()
        comment = Comment(text=request.POST['comment'], order=order)
        comment.save()
        order.summary = summary
        try:
            order.creator = request.POST["user"]
            order.source = 2
        except Exception:
            order.creator = str(request.user)
        order.custom_save()
        return redirect("/")


class FilterView(ListView):
    model = Order
    paginate_by = 50
    template_name = "index.html"
    context_object_name = "results"

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        self.dateFrom = datetime.strptime(self.request.GET["dateFrom"], "%d.%m.%Y")
        self.dateTo = datetime.strptime(self.request.GET["dateTo"], "%d.%m.%Y")
        self.filter_get = str(self.request.GET["filter"].lower()).split(" ")
        self.filter_product = str(self.request.GET["filter_product"].lower()).split(" ")
        if request.GET.get("order-id"):
            return redirect("/order/" + request.GET.get("order-id"))
        return super().dispatch(request, *args, **kwargs)

    def get_summary(self, list_orders):
        summary = 0
        status = False
        for order in list_orders:
            summary += order.get_sum()
            if math.isnan(summary) and not status:
                status = True
        self.summary = summary

    def get_source(self) -> str:
        try:
            source = self.request.GET["source"]
        except Exception as _:
            source = ""
        return source

    def get_queryset(self):
        if not self.request.user.is_superuser:
            list_orders = Order.objects.all().order_by('-id').filter(creator=str(self.request.user))
        else:
            if self.request.GET.get("pharmacy") is not None and self.request.GET.get("pharmacy") != "":
                list_orders = Order.objects.all().order_by('-id').filter(creator=self.request.GET.get("pharmacy"))
            else:
                list_orders = Order.objects.all().order_by('-id')
        list_orders = self.filter_list_orders(list_orders)

        if self.request.GET["provider"] != "":
            list_orders = self.get_orders_by_provider(self.request.GET["provider"], list_orders)
        self.get_summary(list_orders)
        return list_orders

    def filter_list_orders(self, list_orders):
        """
        Method filters orders
        """
        list_orders = list_orders
        if self.get_source() != "":
            list_orders = list_orders.filter(source=int(self.get_source()))
        list_orders = list_orders.filter(date__range=[self.dateFrom, self.dateTo + timedelta(days=1)])
        list_orders = list_orders.order_by('-id')
        for part in self.filter_product:
            if part != "":
                list_orders = list_orders.filter(product__name__icontains=part.lower()).order_by("-id").distinct('id')
        for part in self.filter_get:
            if part == "":
                break
            if is_number(part) is False:
                list_orders = list_orders.filter(purchaser__contains=part.lower()).order_by("-id")
            else:
                list_orders = list_orders.filter(phone__contains=part).order_by("-id")
            list_orders = list_orders.distinct('id')
        if self.request.GET["status"] != "0":
            # list_orders_id = [order.id for order in list_orders if order.get_numeric_status() == self.request.GET["status"]]
            list_orders = list_orders.filter(status=self.request.GET.get("status")).order_by("-id")
        if self.request.GET.get("show_sold") is None and self.request.GET.get("status") == "0":
            list_orders = list_orders.exclude(status="7").exclude(status="8")
        list_orders = list_orders.prefetch_related("product_set", "comment_set")
        return list_orders

    def get_context_data(self, **kwargs):
        context = super(FilterView, self).get_context_data(**kwargs)
        context['providers'] = Product.providers
        context['nums'] = range(0)
        current_url = self.request.get_full_path()
        if "&page=" in current_url:
            context["redir"] = current_url.split("&page=")[0] + "&page="
        else:
            context["redir"] = current_url + "&page="
        paginator: Paginator = context["paginator"]
        dateTo = self.dateTo.strftime("%d.%m.%Y")
        dateFrom = self.dateFrom.strftime("%d.%m.%Y")
        context["length_results"] = paginator.count
        context["summary"] = self.summary
        context["dateFrom"] = dateFrom
        context["dateTo"] = dateTo
        context['show_sold'] = self.request.GET.get("show_sold")
        context['filter'] = self.request.GET["filter"]
        context['nums'] = range(1, paginator.num_pages + 1)
        context['status'] = self.request.GET["status"]
        context["provider"] = self.request.GET["provider"]
        context['statuses'] = Order.statuses
        context['pharmacy_filter'] = self.request.GET.get("pharmacy")
        context["users"] = [str(user) for user in User.objects.filter(is_superuser=False)]
        context["filter_product"] = self.request.GET["filter_product"]
        context["source"] = self.get_source()
        return context

    def get_orders_by_provider(self, provider, orders):
        inet_providers = {
            "1": "Протек", "2": "ПУЛЬС", "3": "Катрен", "4": "Роста",
            "5": "СИА", "6": "Агроресурсы", "8": "КОСМЕТИКА", "9": "Ефимова",
            "11": "Аверсон", "0": "поставщик"
        }
        true_orders = []
        for order in orders:
            products = Product.objects.filter(order=order)
            direct_products = list(products.filter(provider__contains=provider))
            indirect_products = list(products.filter(provider__contains=inet_providers[provider]))
            direct_products.extend(indirect_products)
            if direct_products is None:
                continue
            elif direct_products != [] and order not in true_orders:
                for product in direct_products:
                    if inet_providers[provider] in product.get_provider():
                        true_orders.append(order)
                        break
        return true_orders


class UpdateOrder(UpdateView):
    slug_field = 'product'
    slug_url_kwarg = 'order_id'
    pk_url_kwarg = 'order_id'
    model = Order
    template_name = "order.html"
    fields = ["purchaser", "summary", "status", "phone"]

    def get(self, request, *args, **kwargs):
        true_resp = super().get(request, *args, **kwargs)
        if self.object.creator != request.user.username and not request.user.is_superuser:
            return HttpResponse('Заявка не из вашей аптеки <a href="/">вернутся на главную</a>')
        return true_resp

    def get_context_data(self, **kwargs):
        url_referer = self.request.META["HTTP_REFERER"]
        if "page=" in url_referer \
                or "filter" in url_referer \
                or "http://url/" == url_referer \
                or "http://url/" == url_referer:
            pass
        else:
            try:
                url_referer = self.request.session["url_ref"]
            except KeyError:
                url_referer = "/"

        self.request.session["url_ref"] = url_referer
        context = super().get_context_data(**kwargs)
        product_set = self.object.product_set.all()
        context["products"] = product_set
        comment = self.object.get_comment()
        context['comment'] = comment
        return context

    def post(self, request: HttpRequest, *args, **kwargs):
        order = Order.objects.get(id=int(kwargs['order_id']))
        try:
            comment: Comment = Comment.objects.get(order=order)
            comment.text = request.POST.get("comment")
            if request.POST.get("important") is not None:
                comment.status = True
            else:
                comment.status = False
            comment.save()
        except MultipleObjectsReturned as _:
            Comment.objects.filter(order=order).delete()
            comment = Comment()
            comment.order = order
            comment.text = request.POST.get("comment")
            comment.save()
        for key, val in request.POST.items():
            if "status" in key:
                idp = int(key.split("status")[1])
                product = Product.objects.get(id=idp)
                product.status = val
                product.custom_save()
            elif "purchaser" in key:
                order.purchaser = val
                order.save()
            elif "phone" in key:
                order.phone = val
                order.save()
            elif "provider" in key:
                idp = int(key.split("provider")[1])
                product = Product.objects.get(id=idp)
                product.provider = val
                product.custom_save()
            elif "med" in key:
                idp = int(key.split("med")[1])
                product = Product.objects.get(id=idp)
                product.name = val.lower()
                product.custom_save()
            elif "amount" in key:
                idp = int(key.split("amount")[1])
                product = Product.objects.get(id=idp)
                product.amount = val
                product.custom_save()
            elif "cost" in key:
                idp = int(key.split("cost")[1])
                product = Product.objects.get(id=idp)
                product.cost = val
                product.custom_save()
            elif "ITOG" in key:
                order.summary = val
                order.custom_save()
        return redirect(request.META["HTTP_REFERER"])


class PrintView(ListView):
    def get(self, request, *args, **kwargs):
        context = {}
        printing = request.session["printing"]
        orders = []
        for order_id in printing:
            orders.append(Order.objects.get(id=int(order_id)))
        printing.clear()
        request.session["printing"] = printing
        context["orders"] = orders
        context["user"] = request.user
        return render(request, "print.html", context)


class GraphicView(ListView):
    model = Order
    template_name = "graphic.html"

    def get_context_data(self, **kwargs):
        context = super(GraphicView, self).get_context_data(**kwargs)
        try:
            date_to = datetime.strptime(self.request.GET["dateTo"], "%d.%m.%Y")
            date_from = datetime.strptime(self.request.GET["dateFrom"], "%d.%m.%Y")
            pharms = dict(self.request.GET)["pharms"]
        except Exception:
            date_to = datetime.now().date()
            date_from = date_to - timedelta(days=30)
            pharms = ["sovet"]
        for pharm in pharms:
            if pharm == "common":
                context["common"] = self.get_common_data(date_from, date_to)
                continue
            context["summaries_" + pharm] = self.get_summaries(date_from, date_to, pharm=pharm)
        context["pharms"] = pharms
        context["dates"] = self.get_dates(date_from, date_to)
        context["dateFrom"] = date_from.strftime("%d.%m.%Y")
        context["dateTo"] = date_to.strftime("%d.%m.%Y")
        return context

    def get_dates(self, date_from: datetime, date_to: datetime) -> list:
        orders = Order.objects.all().filter(date__range=[date_from, date_to]).order_by("id")
        dates = list()
        for order in orders:
            date = order.date.strftime("%d.%m.%Y")
            if date not in dates:
                dates.append(date)
        return dates

    def get_summaries(self, date_from, date_to, pharm) -> list:
        summaries = list()
        dates = self.get_dates(date_from, date_to)
        for date in dates:
            orders = Order.objects.filter(
                date__contains=datetime.strptime(date, "%d.%m.%Y").date(),
                creator__contains=pharm
            )
            summary = 0
            for order in orders:
                summary += order.summary
            summaries.append(summary)
        return summaries

    def get_common_data(self, date_from: datetime, date_to: datetime) -> list:
        pharms = ["sovet", "krasn", "jd", "souz"]
        data = list()
        summaries = list()
        for pharm in pharms:
            summaries.append(self.get_summaries(date_from, date_to, pharm))
        for i in zip(summaries[0], summaries[1], summaries[2], summaries[3]):
            data.append(sum(i))
        return data
