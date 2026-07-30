import type { Language } from "../api/types";

type MessageKey =
  | "nav.home"
  | "nav.create"
  | "nav.history"
  | "nav.plans"
  | "nav.profile"
  | "home.tagline"
  | "home.cta"
  | "home.available"
  | "home.eyebrow"
  | "home.titleLead"
  | "home.titleAccent"
  | "home.contactAlt"
  | "home.contactCaption"
  | "home.recipesEyebrow"
  | "home.recipesTitle"
  | "home.archiveEyebrow"
  | "home.archiveTitle"
  | "home.viewAll"
  | "home.archiveEmpty"
  | "home.archiveHelp"
  | "home.chooseStudio"
  | "home.imageStudio"
  | "home.imageStudioHelp"
  | "home.videoStudio"
  | "home.videoStudioHelp"
  | "create.title"
  | "create.subtitle"
  | "create.balance"
  | "create.operationLabel"
  | "create.operationCreate"
  | "create.operationCreateHelp"
  | "create.operationEdit"
  | "create.operationEditHelp"
  | "create.operationUpscale"
  | "create.operationUpscaleHelp"
  | "create.promiseLabel"
  | "create.smart"
  | "create.smartHelp"
  | "create.fast"
  | "create.fastHelp"
  | "create.quality"
  | "create.qualityHelp"
  | "create.smartPickedFast"
  | "create.smartPickedQuality"
  | "create.eta"
  | "create.proControls"
  | "create.proControlsHelp"
  | "create.references"
  | "create.referencesHelp"
  | "create.figure"
  | "create.referencesLimit"
  | "create.addReferences"
  | "create.removeReference"
  | "create.missingReference"
  | "create.upscaleSource"
  | "create.upscaleSourceHelp"
  | "create.upscaleEligibility"
  | "create.upscaleUnverified"
  | "create.upscaleTooLarge"
  | "create.upscalePromise"
  | "create.flavor"
  | "create.flavorPhoto"
  | "create.flavorDenoiser"
  | "create.flavorSublime"
  | "create.sharpen"
  | "create.smartGrain"
  | "create.ultraDetail"
  | "create.quoteLocked"
  | "create.quoteExpired"
  | "create.quoteExpires"
  | "create.quoteError"
  | "create.balanceAfter"
  | "create.upscaleRestored"
  | "create.fromScratch"
  | "create.fromPhoto"
  | "create.reference"
  | "create.referenceHelp"
  | "create.choosePhoto"
  | "create.replacePhoto"
  | "create.removePhoto"
  | "create.uploading"
  | "create.uploadReady"
  | "create.uploadError"
  | "create.invalidType"
  | "create.tooLarge"
  | "create.noReferenceSupport"
  | "create.restoring"
  | "create.restoreError"
  | "create.repeatRestored"
  | "create.remixRestored"
  | "create.modelChanged"
  | "create.referenceExpired"
  | "create.uploadNewPhoto"
  | "create.clearContinuation"
  | "create.modeLabel"
  | "create.simpleHelp"
  | "create.advancedHelp"
  | "create.templatesEyebrow"
  | "create.templatesTitle"
  | "create.templatesCount"
  | "create.useTemplate"
  | "create.intentLabel"
  | "create.referenceAlt"
  | "create.simpleModel"
  | "create.seed"
  | "create.seedHint"
  | "create.photoRequired"
  | "create.model"
  | "create.prompt"
  | "create.promptHint"
  | "create.promptExample"
  | "create.promptLab"
  | "create.promptLabEyebrow"
  | "create.promptLabHelp"
  | "create.promptLabOpen"
  | "create.promptLabClose"
  | "create.assistantIntent"
  | "create.intentGeneral"
  | "create.intentProduct"
  | "create.intentSocial"
  | "create.intentPortrait"
  | "create.intentInterior"
  | "create.intentFood"
  | "create.intentFashion"
  | "create.assistantPrice"
  | "create.assistantChargeRule"
  | "create.assistantImprove"
  | "create.assistantImproving"
  | "create.assistantProposal"
  | "create.assistantProposalHelp"
  | "create.assistantOriginal"
  | "create.assistantVersion"
  | "create.assistantApply"
  | "create.assistantKeep"
  | "create.assistantUndo"
  | "create.assistantCropped"
  | "create.assistantEmpty"
  | "create.assistantTooLong"
  | "create.assistantInsufficient"
  | "create.assistantRateError"
  | "create.assistantProviderError"
  | "create.assistantGenericError"
  | "create.suggestionLight"
  | "create.suggestionDetail"
  | "create.suggestionComposition"
  | "create.suggestionTexture"
  | "create.settings"
  | "create.simple"
  | "create.advanced"
  | "create.resolution"
  | "create.aspect"
  | "create.quote"
  | "create.quoteLoading"
  | "create.submit"
  | "create.submitWithPrice"
  | "create.creating"
  | "create.credits"
  | "create.insufficient"
  | "create.noModels"
  | "video.title"
  | "video.subtitle"
  | "video.modeLabel"
  | "video.textMode"
  | "video.textModeHelp"
  | "video.photoMode"
  | "video.photoModeHelp"
  | "video.promiseLabel"
  | "video.smartPickedFast"
  | "video.smartPickedQuality"
  | "video.recipesEyebrow"
  | "video.recipesTitle"
  | "video.photoTitle"
  | "video.photoHelp"
  | "video.choosePhoto"
  | "video.replacePhoto"
  | "video.removePhoto"
  | "video.uploading"
  | "video.uploadReady"
  | "video.invalidType"
  | "video.tooLarge"
  | "video.uploadError"
  | "video.photoRequired"
  | "video.prompt"
  | "video.promptHint"
  | "video.promptGuide"
  | "video.format"
  | "video.duration"
  | "video.seconds"
  | "video.advanced"
  | "video.advancedHelp"
  | "video.model"
  | "video.resolution"
  | "video.seed"
  | "video.refund"
  | "video.submit"
  | "video.submitWithPrice"
  | "video.creating"
  | "video.noModels"
  | "video.restoring"
  | "video.restoreError"
  | "video.repeatRestored"
  | "video.fromFrameRestored"
  | "video.clearContinuation"
  | "generation.title"
  | "generation.activeTitle"
  | "generation.activeBody"
  | "generation.cancel"
  | "generation.done"
  | "generation.doneBody"
  | "generation.failed"
  | "generation.failedBody"
  | "generation.cancelled"
  | "generation.cancelledBody"
  | "generation.download"
  | "generation.repeat"
  | "generation.remix"
  | "generation.upscale"
  | "generation.share"
  | "generation.sharing"
  | "generation.shareFailed"
  | "generation.shareUnsupported"
  | "generation.newWork"
  | "generation.resultAlt"
  | "generation.refresh"
  | "generation.unavailableTitle"
  | "generation.unavailableBody"
  | "generation.backToHistory"
  | "generation.createImage"
  | "generation.createVideo"
  | "generation.routeImage"
  | "generation.routeVideo"
  | "generation.routeUpscale"
  | "generation.details"
  | "generation.model"
  | "generation.price"
  | "generation.videoTitle"
  | "generation.videoActiveTitle"
  | "generation.videoActiveBody"
  | "generation.videoDone"
  | "generation.videoDoneBody"
  | "generation.videoResultAlt"
  | "generation.makeFromFrame"
  | "generation.newPhotoVideo"
  | "generation.stageQueued"
  | "generation.stageSubmitting"
  | "generation.stageRunning"
  | "generation.stageFinalizing"
  | "generation.etaRemaining"
  | "history.title"
  | "history.empty"
  | "history.eyebrow"
  | "history.subtitle"
  | "history.ready"
  | "history.active"
  | "history.failed"
  | "history.cancelled"
  | "history.noPreview"
  | "history.videoPreview"
  | "history.imageWork"
  | "history.videoWork"
  | "history.previewAlt"
  | "history.credits"
  | "history.itemOpen"
  | "history.filterLabel"
  | "history.filterAll"
  | "history.filterImage"
  | "history.filterVideo"
  | "history.filterActive"
  | "history.filterEmpty"
  | "plans.title"
  | "plans.body"
  | "plans.badge"
  | "plans.subtitle"
  | "plans.credits"
  | "plans.pay"
  | "plans.opening"
  | "plans.recommended"
  | "plans.terms"
  | "plans.openTerms"
  | "plans.termsAccepted"
  | "plans.termsRequired"
  | "plans.unavailable"
  | "plans.history"
  | "plans.emptyHistory"
  | "plans.pending"
  | "plans.paid"
  | "plans.cancelled"
  | "plans.invoiceFailed"
  | "profile.title"
  | "profile.eyebrow"
  | "profile.subtitle"
  | "profile.anonymous"
  | "profile.walletEyebrow"
  | "profile.walletTitle"
  | "profile.available"
  | "profile.topUp"
  | "profile.preferencesEyebrow"
  | "profile.preferencesTitle"
  | "profile.languageHelp"
  | "profile.trustEyebrow"
  | "profile.trustTitle"
  | "profile.support"
  | "profile.supportHelp"
  | "profile.purchases"
  | "profile.purchasesHelp"
  | "profile.terms"
  | "profile.termsHelp"
  | "profile.language"
  | "profile.plan"
  | "profile.balance"
  | "profile.reserved"
  | "profile.notifications"
  | "profile.readyNotifications"
  | "profile.readyNotificationsHelp"
  | "profile.notificationUpdateError"
  | "common.retry"
  | "common.offline"
  | "common.error"
  | "common.loading"
  | "auth.booting"
  | "auth.failed"
  | "auth.configurationError"
  | "auth.networkError"
  | "auth.openInTelegram"
  | "auth.unknownError";

const ru: Record<MessageKey, string> = {
  "nav.home": "Главная",
  "nav.create": "Создать",
  "nav.history": "История",
  "nav.plans": "Планы",
  "nav.profile": "Профиль",
  "home.tagline": "Изображения и видео для брендов, товаров и идей. Точная цена и срок — до запуска.",
  "home.cta": "Создать",
  "home.available": "Доступно",
  "home.eyebrow": "Креативная AI-студия · Казахстан",
  "home.titleLead": "Создавайте визуалы,",
  "home.titleAccent": "которые работают.",
  "home.contactAlt": "Подборка работ KELBET: товар, кафе, мода и городской пейзаж",
  "home.contactCaption": "Живой контактный лист студии",
  "home.recipesEyebrow": "Локальные сценарии",
  "home.recipesTitle": "Начните с готового брифа",
  "home.archiveEyebrow": "Ваше пространство",
  "home.archiveTitle": "Последние работы",
  "home.viewAll": "Все работы",
  "home.archiveEmpty": "Архив готов к первой работе",
  "home.archiveHelp": "Здесь появятся готовые кадры и ролики",
  "home.chooseStudio": "Выберите студию",
  "home.imageStudio": "Image Studio",
  "home.imageStudioHelp": "Создание, редактирование и увеличение изображений",
  "home.videoStudio": "Video Studio",
  "home.videoStudioHelp": "Ролики из текста или одного фото для соцсетей и бизнеса",
  "create.title": "Создать изображение",
  "create.subtitle": "Опишите идею — остальное соберём в студии",
  "create.balance": "Баланс",
  "create.operationLabel": "Задача",
  "create.operationCreate": "Создать",
  "create.operationCreateHelp": "Новый кадр из текста",
  "create.operationEdit": "Редактировать",
  "create.operationEditHelp": "Собрать до 10 референсов",
  "create.operationUpscale": "Upscale 2×",
  "create.operationUpscaleHelp": "Увеличить и восстановить",
  "create.promiseLabel": "Обещание студии",
  "create.smart": "Smart",
  "create.smartHelp": "Подберём по задаче",
  "create.fast": "Fast",
  "create.fastHelp": "Быстрее в работу",
  "create.quality": "Quality",
  "create.qualityHelp": "Точнее и детальнее",
  "create.smartPickedFast": "Smart выбрал быстрый проход",
  "create.smartPickedQuality": "Smart выбрал качественный проход",
  "create.eta": "Обычно",
  "create.proControls": "Pro-контроль",
  "create.proControlsHelp": "Модель и точные параметры",
  "create.references": "Контактный лист",
  "create.referencesHelp": "В промпте называйте их Figure 1, Figure 2 и далее.",
  "create.figure": "Figure",
  "create.referencesLimit": "Максимум референсов",
  "create.addReferences": "Добавить изображения",
  "create.removeReference": "Убрать референс",
  "create.missingReference": "Добавьте хотя бы один готовый референс",
  "create.upscaleSource": "Исходное изображение",
  "create.upscaleSourceHelp": "Один кадр для точного восстановления",
  "create.upscaleEligibility": "Источник до 2048×2048 · результат 2×",
  "create.upscaleUnverified": "Не удалось проверить размер изображения. Выберите другой файл.",
  "create.upscaleTooLarge": "Источник больше 2048×2048. Уменьшите его перед запуском.",
  "create.upscalePromise": "Precision 2×",
  "create.flavor": "Характер восстановления",
  "create.flavorPhoto": "Натуральное фото",
  "create.flavorDenoiser": "Старое или шумное фото",
  "create.flavorSublime": "Иллюстрация и дизайн",
  "create.sharpen": "Резкость",
  "create.smartGrain": "Умное зерно",
  "create.ultraDetail": "Ультрадеталь",
  "create.quoteLocked": "Цена зафиксирована",
  "create.quoteExpired": "Цена обновляется",
  "create.quoteExpires": "ещё",
  "create.quoteError": "Не удалось получить цену",
  "create.balanceAfter": "Останется",
  "create.upscaleRestored": "Готовый результат добавлен для увеличения 2×",
  "create.fromScratch": "С нуля",
  "create.fromPhoto": "По фото",
  "create.reference": "Фото-основа",
  "create.referenceHelp": "JPG, PNG или WebP · до 10 МБ",
  "create.choosePhoto": "Выбрать фото",
  "create.replacePhoto": "Заменить",
  "create.removePhoto": "Удалить",
  "create.uploading": "Загружаем фото…",
  "create.uploadReady": "Фото готово",
  "create.uploadError": "Не удалось загрузить фото. Попробуйте другое.",
  "create.invalidType": "Подойдёт JPG, PNG или WebP.",
  "create.tooLarge": "Фото должно быть меньше 10 МБ.",
  "create.noReferenceSupport": "Эта модель создаёт только с нуля. Выберите другую модель.",
  "create.restoring": "Восстанавливаем творческий черновик…",
  "create.restoreError": "Не удалось восстановить эту работу",
  "create.repeatRestored": "Настройки восстановлены — проверьте и запустите снова",
  "create.remixRestored": "Готовый результат добавлен как основа варианта",
  "create.modelChanged": "Исходная модель недоступна — выбрана актуальная замена. Цена рассчитана заново.",
  "create.referenceExpired": "Старое фото больше недоступно. Загрузите новое, чтобы продолжить по фото.",
  "create.uploadNewPhoto": "Загрузить новое фото",
  "create.clearContinuation": "Закрыть сообщение о восстановлении",
  "create.modeLabel": "Режим студии",
  "create.simpleHelp": "Сценарии и только важные настройки",
  "create.advancedHelp": "Модель, качество и точные параметры",
  "create.templatesEyebrow": "Творческие рецепты",
  "create.templatesTitle": "Начните с готового брифа",
  "create.templatesCount": "6 сценариев",
  "create.useTemplate": "Выбрать шаблон",
  "create.intentLabel": "Способ создания",
  "create.referenceAlt": "Фото-основа для нового изображения",
  "create.simpleModel": "Модель подобрана автоматически",
  "create.seed": "Seed",
  "create.seedHint": "Случайный",
  "create.photoRequired": "Добавьте фото, чтобы запустить создание",
  "create.model": "Модель",
  "create.prompt": "Что хотите увидеть?",
  "create.promptHint": "Например: рекламное фото керамической чашки на тёплом песочном фоне",
  "create.promptExample": "Добавьте к описанию",
  "create.promptLab": "KELBET Prompt Lab",
  "create.promptLabEyebrow": "Инструмент студии",
  "create.promptLabHelp": "Уточнит свет, композицию и детали, сохранив вашу идею.",
  "create.promptLabOpen": "Открыть",
  "create.promptLabClose": "Свернуть",
  "create.assistantIntent": "Для чего создаём",
  "create.intentGeneral": "Любая идея",
  "create.intentProduct": "Товар",
  "create.intentSocial": "Соцсети",
  "create.intentPortrait": "Портрет",
  "create.intentInterior": "Интерьер",
  "create.intentFood": "Еда",
  "create.intentFashion": "Мода",
  "create.assistantPrice": "Улучшить за",
  "create.assistantChargeRule": "Кредит спишется только если улучшенная версия готова.",
  "create.assistantImprove": "Улучшить описание",
  "create.assistantImproving": "Собираем сильный бриф…",
  "create.assistantProposal": "Предложение Prompt Lab",
  "create.assistantProposalHelp": "Сравните с вашим текстом — ничего не заменится без подтверждения.",
  "create.assistantOriginal": "Ваш текст",
  "create.assistantVersion": "Версия Lab",
  "create.assistantApply": "Применить",
  "create.assistantKeep": "Оставить мой",
  "create.assistantUndo": "Вернуть мой текст",
  "create.assistantCropped": "Версия сокращена под лимит выбранной модели.",
  "create.assistantEmpty": "Сначала опишите идею выше.",
  "create.assistantTooLong": "Сократите описание до лимита Prompt Lab.",
  "create.assistantInsufficient": "Для Prompt Lab не хватает кредитов.",
  "create.assistantRateError": "Слишком много запросов. Подождите немного и попробуйте снова.",
  "create.assistantProviderError": "Prompt Lab временно отдыхает. Ваш текст сохранён.",
  "create.assistantGenericError": "Не удалось улучшить описание. Ваш текст не изменился.",
  "create.suggestionLight": "мягкий дневной свет",
  "create.suggestionDetail": "высокая детализация",
  "create.suggestionComposition": "чистая композиция",
  "create.suggestionTexture": "натуральные текстуры",
  "create.settings": "Настройки",
  "create.simple": "Просто",
  "create.advanced": "Точно",
  "create.resolution": "Качество",
  "create.aspect": "Формат",
  "create.quote": "Итоговая цена",
  "create.quoteLoading": "Уточняем цену…",
  "create.submit": "Создать изображение",
  "create.submitWithPrice": "Создать за",
  "create.creating": "Запускаем…",
  "create.credits": "кредитов",
  "create.insufficient": "Недостаточно кредитов",
  "create.noModels": "Сейчас нет доступных моделей изображений",
  "video.title": "Создать видео",
  "video.subtitle": "Соберите короткую сцену — от идеи до готового ролика",
  "video.modeLabel": "Откуда начинаем",
  "video.textMode": "Из текста",
  "video.textModeHelp": "Опишите всю сцену словами",
  "video.photoMode": "Оживить фото",
  "video.photoModeHelp": "Добавьте один исходный кадр",
  "video.promiseLabel": "Темп студии",
  "video.smartPickedFast": "Smart выбрал быстрый рендер",
  "video.smartPickedQuality": "Smart выбрал детальный рендер",
  "video.recipesEyebrow": "Локальные рецепты",
  "video.recipesTitle": "Выберите раскадровку",
  "video.photoTitle": "Исходный кадр",
  "video.photoHelp": "JPG, PNG или WebP · один файл до 10 МБ",
  "video.choosePhoto": "Выбрать фото",
  "video.replacePhoto": "Заменить",
  "video.removePhoto": "Удалить",
  "video.uploading": "Загружаем кадр…",
  "video.uploadReady": "Кадр готов",
  "video.invalidType": "Подойдёт JPG, PNG или WebP.",
  "video.tooLarge": "Фото должно быть меньше 10 МБ.",
  "video.uploadError": "Не удалось загрузить фото. Попробуйте другое.",
  "video.photoRequired": "Добавьте готовый кадр для запуска.",
  "video.prompt": "Режиссёрский бриф",
  "video.promptHint": "Например: керамическая чашка поворачивается к камере, медленный наезд, тёплый утренний свет, тихий звук кофейни",
  "video.promptGuide": "Объект → действие → камера → атмосфера → звук",
  "video.format": "Формат",
  "video.duration": "Длительность",
  "video.seconds": "сек",
  "video.advanced": "Точные настройки",
  "video.advancedHelp": "Модель, 720p и воспроизводимый seed",
  "video.model": "Модель",
  "video.resolution": "Разрешение",
  "video.seed": "Seed",
  "video.refund": "При техническом сбое кредиты вернутся автоматически.",
  "video.submit": "Создать видео",
  "video.submitWithPrice": "Создать за",
  "video.creating": "Запускаем сцену…",
  "video.noModels": "Сейчас нет доступных моделей видео",
  "video.restoring": "Восстанавливаем сцену…",
  "video.restoreError": "Не удалось восстановить эту работу",
  "video.repeatRestored": "Сцена и настройки восстановлены — проверьте перед запуском",
  "video.fromFrameRestored": "Готовый кадр добавлен как основа нового видео",
  "video.clearContinuation": "Закрыть сообщение о восстановлении",
  "generation.title": "Ваша работа",
  "generation.activeTitle": "Создаём изображение",
  "generation.activeBody": "Собираем композицию и детали. Можно спокойно оставить экран открытым.",
  "generation.cancel": "Отменить создание",
  "generation.done": "Изображение готово",
  "generation.doneBody": "Сохраните результат или начните новую работу.",
  "generation.failed": "Не получилось создать",
  "generation.failedBody": "Кредиты не пропадут. Вернитесь в студию и попробуйте снова.",
  "generation.cancelled": "Создание отменено",
  "generation.cancelledBody": "Можно вернуться и запустить новую идею.",
  "generation.download": "Скачать",
  "generation.repeat": "Повторить",
  "generation.remix": "Сделать вариант",
  "generation.upscale": "Upscale 2×",
  "generation.share": "Поделиться",
  "generation.sharing": "Готовим файл…",
  "generation.shareFailed": "Не удалось открыть системное меню. Файл можно скачать.",
  "generation.shareUnsupported": "На этом устройстве можно скачать файл и отправить вручную.",
  "generation.newWork": "Новая работа",
  "generation.resultAlt": "Готовое изображение KELBET",
  "generation.refresh": "Обновить ссылку",
  "generation.unavailableTitle": "Работа недоступна",
  "generation.unavailableBody": "Ссылка могла устареть или работа была удалена. Откройте архив либо начните новую.",
  "generation.backToHistory": "Открыть мои работы",
  "generation.createImage": "Создать изображение",
  "generation.createVideo": "Создать видео",
  "generation.routeImage": "KELBET Image",
  "generation.routeVideo": "KELBET Motion",
  "generation.routeUpscale": "KELBET Upscale",
  "generation.details": "Детали работы",
  "generation.model": "Маршрут студии",
  "generation.price": "Цена",
  "generation.videoTitle": "Ваш ролик",
  "generation.videoActiveTitle": "Снимаем сцену",
  "generation.videoActiveBody": "Собираем движение по кадрам. Можно уйти — Telegram сообщит о готовности.",
  "generation.videoDone": "Видео готово",
  "generation.videoDoneBody": "Посмотрите ролик, скачайте его или создайте новый из своей фотографии.",
  "generation.videoResultAlt": "Готовое видео KELBET",
  "generation.makeFromFrame": "Оживить кадр",
  "generation.newPhotoVideo": "Новое видео из фото",
  "generation.stageQueued": "Сцена в очереди",
  "generation.stageSubmitting": "Передаём режиссёрский бриф",
  "generation.stageRunning": "Строим движение по кадрам",
  "generation.stageFinalizing": "Собираем финальный ролик",
  "generation.etaRemaining": "Осталось примерно",
  "history.title": "История",
  "history.empty": "Пока пусто — создайте первую работу",
  "history.eyebrow": "Архив студии",
  "history.subtitle": "Ваши визуальные эксперименты, собранные в одном месте.",
  "history.ready": "Готово",
  "history.active": "Создаётся",
  "history.failed": "Не получилось",
  "history.cancelled": "Отменено",
  "history.noPreview": "Без превью",
  "history.videoPreview": "Видео",
  "history.imageWork": "KELBET Image",
  "history.videoWork": "KELBET Motion",
  "history.previewAlt": "Превью работы KELBET",
  "history.credits": "кр.",
  "history.itemOpen": "Открыть работу",
  "history.filterLabel": "Фильтр работ",
  "history.filterAll": "Все",
  "history.filterImage": "Изображения",
  "history.filterVideo": "Видео",
  "history.filterActive": "В работе",
  "history.filterEmpty": "В этой категории пока нет работ",
  "plans.title": "Планы",
  "plans.body": "Покупка цифровых кредитов через безопасный счёт Telegram Stars.",
  "plans.badge": "Telegram Stars",
  "plans.subtitle": "Цена фиксируется в заказе и не меняется после открытия счёта.",
  "plans.credits": "кредитов",
  "plans.pay": "Купить за {stars} ⭐",
  "plans.opening": "Открываем счёт…",
  "plans.recommended": "Рекомендуем",
  "plans.terms": "Я прочитал(а) и принимаю условия покупки и возврата",
  "plans.openTerms": "Открыть условия",
  "plans.termsAccepted": "Условия приняты — можно выбрать пакет.",
  "plans.termsRequired": "Сначала подтвердите условия покупки.",
  "plans.unavailable": "Оплата временно закрыта до завершения проверки условий и поддержки.",
  "plans.history": "История покупок",
  "plans.emptyHistory": "Покупок пока нет",
  "plans.pending": "Ожидает оплаты",
  "plans.paid": "Оплачено",
  "plans.cancelled": "Отменено",
  "plans.invoiceFailed": "Не удалось открыть счёт. Попробуйте ещё раз.",
  "profile.title": "Профиль",
  "profile.eyebrow": "Аккаунт студии",
  "profile.subtitle": "Баланс, язык, уведомления и помощь — в одном месте.",
  "profile.anonymous": "Пользователь KELBET",
  "profile.walletEyebrow": "Кредиты",
  "profile.walletTitle": "Кошелёк студии",
  "profile.available": "Доступно",
  "profile.topUp": "Пополнить",
  "profile.preferencesEyebrow": "Персонализация",
  "profile.preferencesTitle": "Настройки",
  "profile.languageHelp": "Интерфейс и сообщения бота",
  "profile.trustEyebrow": "Доверие и помощь",
  "profile.trustTitle": "Поддержка",
  "profile.support": "Помощь команды",
  "profile.supportHelp": "Напишите команду в чате с ботом",
  "profile.purchases": "Покупки и кредиты",
  "profile.purchasesHelp": "Пакеты, статусы и история",
  "profile.terms": "Условия покупки",
  "profile.termsHelp": "Оплата, возвраты и поддержка",
  "profile.language": "Язык",
  "profile.plan": "План",
  "profile.balance": "Баланс",
  "profile.reserved": "В резерве",
  "profile.notifications": "Уведомления",
  "profile.readyNotifications": "Результат готов",
  "profile.readyNotificationsHelp": "KELBET пришлёт сообщение в Telegram, когда создание завершится.",
  "profile.notificationUpdateError": "Не удалось сохранить настройку. Попробуйте ещё раз.",
  "common.retry": "Повторить",
  "common.offline": "Нет сети — показаны последние данные",
  "common.error": "Что-то пошло не так",
  "common.loading": "Загрузка…",
  "auth.booting": "Открываем KELBET…",
  "auth.failed": "Не удалось войти через Telegram",
  "auth.configurationError":
    "Mini App собран с неверным адресом API. Укажите реальный Railway URL в Vercel и выполните Redeploy.",
  "auth.networkError":
    "Нет связи с сервером KELBET. Проверьте, что Railway API запущен и его HTTPS-адрес указан в Vercel.",
  "auth.openInTelegram": "Откройте KELBET кнопкой внутри Telegram.",
  "auth.unknownError": "Неизвестная ошибка авторизации. Повторите попытку.",
};

const kk: Record<MessageKey, string> = {
  "nav.home": "Басты",
  "nav.create": "Жасау",
  "nav.history": "Тарих",
  "nav.plans": "Жоспарлар",
  "nav.profile": "Кабинет",
  "home.tagline": "Брендке, тауарға және идеяға арналған сурет пен бейне. Нақты баға мен мерзім — бастамай тұрып.",
  "home.cta": "Жасау",
  "home.available": "Қолжетімді",
  "home.eyebrow": "Шығармашылық AI шеберхана · Қазақстан",
  "home.titleLead": "Нәтиже беретін",
  "home.titleAccent": "визуал жасаңыз.",
  "home.contactAlt": "KELBET жұмыстары: тауар, кафе, сән және қала көрінісі",
  "home.contactCaption": "Шеберхананың жанды кадрлар топтамасы",
  "home.recipesEyebrow": "Жергілікті сценарийлер",
  "home.recipesTitle": "Дайын брифтен бастаңыз",
  "home.archiveEyebrow": "Сіздің кеңістігіңіз",
  "home.archiveTitle": "Соңғы жұмыстар",
  "home.viewAll": "Барлық жұмыс",
  "home.archiveEmpty": "Архив алғашқы жұмысқа дайын",
  "home.archiveHelp": "Дайын кадрлар мен бейнелер осында көрінеді",
  "home.chooseStudio": "Шеберхананы таңдаңыз",
  "home.imageStudio": "Image Studio",
  "home.imageStudioHelp": "Сурет жасау, өңдеу және үлкейту",
  "home.videoStudio": "Video Studio",
  "home.videoStudioHelp": "Әлеуметтік желі мен бизнеске мәтіннен не фотодан бейне жасау",
  "create.title": "Сурет жасау",
  "create.subtitle": "Ойыңызды сипаттаңыз — қалғанын студияда жинаймыз",
  "create.balance": "Баланс",
  "create.operationLabel": "Тапсырма",
  "create.operationCreate": "Жасау",
  "create.operationCreateHelp": "Мәтіннен жаңа кадр",
  "create.operationEdit": "Өңдеу",
  "create.operationEditHelp": "10 референске дейін біріктіру",
  "create.operationUpscale": "2× үлкейту",
  "create.operationUpscaleHelp": "Үлкейтіп, қалпына келтіру",
  "create.promiseLabel": "Студия уәдесі",
  "create.smart": "Smart",
  "create.smartHelp": "Тапсырмаға сай таңдаймыз",
  "create.fast": "Fast",
  "create.fastHelp": "Нәтиже тезірек",
  "create.quality": "Quality",
  "create.qualityHelp": "Дәл әрі егжей-тегжейлі",
  "create.smartPickedFast": "Smart жылдам өтуді таңдады",
  "create.smartPickedQuality": "Smart сапалы өтуді таңдады",
  "create.eta": "Әдетте",
  "create.proControls": "Pro-басқару",
  "create.proControlsHelp": "Модель және дәл параметрлер",
  "create.references": "Байланыс парағы",
  "create.referencesHelp": "Промптта 1-сурет, 2-сурет деп атаңыз.",
  "create.figure": "Сурет",
  "create.referencesLimit": "Референс санының шегі",
  "create.addReferences": "Суреттер қосу",
  "create.removeReference": "Референсті алып тастау",
  "create.missingReference": "Кемінде бір дайын референс қосыңыз",
  "create.upscaleSource": "Бастапқы сурет",
  "create.upscaleSourceHelp": "Дәл қалпына келтіруге бір кадр",
  "create.upscaleEligibility": "Дереккөз 2048×2048 дейін · нәтиже 2×",
  "create.upscaleUnverified": "Сурет өлшемін тексеру мүмкін болмады. Басқа файл таңдаңыз.",
  "create.upscaleTooLarge": "Дереккөз 2048×2048-ден үлкен. Іске қосар алдында кішірейтіңіз.",
  "create.upscalePromise": "Precision 2×",
  "create.flavor": "Қалпына келтіру сипаты",
  "create.flavorPhoto": "Табиғи фото",
  "create.flavorDenoiser": "Ескі не шулы фото",
  "create.flavorSublime": "Иллюстрация және дизайн",
  "create.sharpen": "Айқындық",
  "create.smartGrain": "Ақылды түйіршік",
  "create.ultraDetail": "Ультрадеталь",
  "create.quoteLocked": "Баға бекітілді",
  "create.quoteExpired": "Баға жаңартылуда",
  "create.quoteExpires": "тағы",
  "create.quoteError": "Бағаны алу мүмкін болмады",
  "create.balanceAfter": "Қалады",
  "create.upscaleRestored": "Дайын нәтиже 2× үлкейтуге қосылды",
  "create.fromScratch": "Нөлден",
  "create.fromPhoto": "Фотомен",
  "create.reference": "Негізгі фото",
  "create.referenceHelp": "JPG, PNG немесе WebP · 10 МБ дейін",
  "create.choosePhoto": "Фото таңдау",
  "create.replacePhoto": "Ауыстыру",
  "create.removePhoto": "Өшіру",
  "create.uploading": "Фото жүктелуде…",
  "create.uploadReady": "Фото дайын",
  "create.uploadError": "Фото жүктелмеді. Басқасын қолданып көріңіз.",
  "create.invalidType": "JPG, PNG немесе WebP форматын таңдаңыз.",
  "create.tooLarge": "Фото 10 МБ-тан кіші болуы керек.",
  "create.noReferenceSupport": "Бұл модель тек нөлден жасайды. Басқа модельді таңдаңыз.",
  "create.restoring": "Шығармашылық нобай қалпына келтірілуде…",
  "create.restoreError": "Бұл жұмысты қалпына келтіру мүмкін болмады",
  "create.repeatRestored": "Баптаулар қалпына келді — тексеріп, қайта іске қосыңыз",
  "create.remixRestored": "Дайын нәтиже жаңа нұсқаның негізі ретінде қосылды",
  "create.modelChanged": "Бастапқы модель қолжетімсіз — өзекті баламасы таңдалды. Баға қайта есептелді.",
  "create.referenceExpired": "Ескі фото енді қолжетімсіз. Фотомен жалғастыру үшін жаңасын жүктеңіз.",
  "create.uploadNewPhoto": "Жаңа фото жүктеу",
  "create.clearContinuation": "Қалпына келтіру хабарын жабу",
  "create.modeLabel": "Студия режимі",
  "create.simpleHelp": "Дайын сценарийлер мен негізгі баптаулар",
  "create.advancedHelp": "Модель, сапа және дәл параметрлер",
  "create.templatesEyebrow": "Шығармашылық рецепттер",
  "create.templatesTitle": "Дайын брифтен бастаңыз",
  "create.templatesCount": "6 сценарий",
  "create.useTemplate": "Үлгіні таңдау",
  "create.intentLabel": "Жасау тәсілі",
  "create.referenceAlt": "Жаңа суретке арналған негізгі фото",
  "create.simpleModel": "Модель автоматты таңдалды",
  "create.seed": "Seed",
  "create.seedHint": "Кездейсоқ",
  "create.photoRequired": "Жасауды бастау үшін фото қосыңыз",
  "create.model": "Модель",
  "create.prompt": "Нені көргіңіз келеді?",
  "create.promptHint": "Мысалы: жылы құм түсті фонда керамикалық кесенің жарнамалық фотосы",
  "create.promptExample": "Сипаттамаға қосыңыз",
  "create.promptLab": "KELBET Prompt Lab",
  "create.promptLabEyebrow": "Студия құралы",
  "create.promptLabHelp": "Ойыңызды сақтап, жарық, композиция және детальдарды нақтылайды.",
  "create.promptLabOpen": "Ашу",
  "create.promptLabClose": "Жинау",
  "create.assistantIntent": "Не үшін жасаймыз",
  "create.intentGeneral": "Кез келген ой",
  "create.intentProduct": "Тауар",
  "create.intentSocial": "Әлеуметтік желі",
  "create.intentPortrait": "Портрет",
  "create.intentInterior": "Интерьер",
  "create.intentFood": "Тағам",
  "create.intentFashion": "Сән",
  "create.assistantPrice": "Жақсарту бағасы",
  "create.assistantChargeRule": "Кредит жақсартылған нұсқа дайын болғанда ғана есептен алынады.",
  "create.assistantImprove": "Сипаттаманы жақсарту",
  "create.assistantImproving": "Нақты бриф құрастырып жатырмыз…",
  "create.assistantProposal": "Prompt Lab ұсынысы",
  "create.assistantProposalHelp": "Өз мәтініңізбен салыстырыңыз — растаусыз ештеңе ауыспайды.",
  "create.assistantOriginal": "Сіздің мәтініңіз",
  "create.assistantVersion": "Lab нұсқасы",
  "create.assistantApply": "Қолдану",
  "create.assistantKeep": "Өзімді қалдыру",
  "create.assistantUndo": "Өз мәтінімді қайтару",
  "create.assistantCropped": "Нұсқа таңдалған модель лимитіне сай қысқартылды.",
  "create.assistantEmpty": "Алдымен жоғарыда ойыңызды сипаттаңыз.",
  "create.assistantTooLong": "Сипаттаманы Prompt Lab лимитіне дейін қысқартыңыз.",
  "create.assistantInsufficient": "Prompt Lab үшін кредит жеткіліксіз.",
  "create.assistantRateError": "Сұрау тым көп. Сәл күтіп, қайта көріңіз.",
  "create.assistantProviderError": "Prompt Lab уақытша демалып жатыр. Мәтініңіз сақталды.",
  "create.assistantGenericError": "Сипаттаманы жақсарту мүмкін болмады. Мәтініңіз өзгермеді.",
  "create.suggestionLight": "жұмсақ күндізгі жарық",
  "create.suggestionDetail": "жоғары детализация",
  "create.suggestionComposition": "таза композиция",
  "create.suggestionTexture": "табиғи текстуралар",
  "create.settings": "Баптаулар",
  "create.simple": "Оңай",
  "create.advanced": "Дәл",
  "create.resolution": "Сапа",
  "create.aspect": "Пішім",
  "create.quote": "Жалпы баға",
  "create.quoteLoading": "Бағаны нақтылаудамыз…",
  "create.submit": "Сурет жасау",
  "create.submitWithPrice": "Жасау бағасы",
  "create.creating": "Іске қосылуда…",
  "create.credits": "кредит",
  "create.insufficient": "Кредит жеткіліксіз",
  "create.noModels": "Қазір сурет модельдері қолжетімсіз",
  "video.title": "Бейне жасау",
  "video.subtitle": "Ойдан дайын роликке дейін қысқа көрініс құрастырыңыз",
  "video.modeLabel": "Неден бастаймыз",
  "video.textMode": "Мәтіннен",
  "video.textModeHelp": "Көріністі толық сөзбен сипаттаңыз",
  "video.photoMode": "Фотоны жандандыру",
  "video.photoModeHelp": "Бір бастапқы кадр қосыңыз",
  "video.promiseLabel": "Студия қарқыны",
  "video.smartPickedFast": "Smart жылдам рендерді таңдады",
  "video.smartPickedQuality": "Smart егжей-тегжейлі рендерді таңдады",
  "video.recipesEyebrow": "Жергілікті рецепттер",
  "video.recipesTitle": "Кадр жоспарын таңдаңыз",
  "video.photoTitle": "Бастапқы кадр",
  "video.photoHelp": "JPG, PNG немесе WebP · 10 МБ дейін бір файл",
  "video.choosePhoto": "Фото таңдау",
  "video.replacePhoto": "Ауыстыру",
  "video.removePhoto": "Өшіру",
  "video.uploading": "Кадр жүктелуде…",
  "video.uploadReady": "Кадр дайын",
  "video.invalidType": "JPG, PNG немесе WebP форматын таңдаңыз.",
  "video.tooLarge": "Фото 10 МБ-тан кіші болуы керек.",
  "video.uploadError": "Фото жүктелмеді. Басқасын қолданып көріңіз.",
  "video.photoRequired": "Іске қосу үшін дайын кадр қосыңыз.",
  "video.prompt": "Режиссерлік бриф",
  "video.promptHint": "Мысалы: керамикалық кесе камераға бұрылады, баяу жақындау, жылы таңғы жарық, кофехананың тыныш дыбысы",
  "video.promptGuide": "Нысан → әрекет → камера → атмосфера → дыбыс",
  "video.format": "Пішім",
  "video.duration": "Ұзақтығы",
  "video.seconds": "сек",
  "video.advanced": "Дәл баптаулар",
  "video.advancedHelp": "Модель, 720p және қайталанатын seed",
  "video.model": "Модель",
  "video.resolution": "Ажыратымдылық",
  "video.seed": "Seed",
  "video.refund": "Техникалық ақауда кредит автоматты түрде қайтарылады.",
  "video.submit": "Бейне жасау",
  "video.submitWithPrice": "Жасау бағасы",
  "video.creating": "Көрініс іске қосылуда…",
  "video.noModels": "Қазір бейне модельдері қолжетімсіз",
  "video.restoring": "Көрініс қалпына келтірілуде…",
  "video.restoreError": "Бұл жұмысты қалпына келтіру мүмкін болмады",
  "video.repeatRestored": "Көрініс пен баптаулар қалпына келді — іске қосар алдында тексеріңіз",
  "video.fromFrameRestored": "Дайын кадр жаңа бейненің негізі ретінде қосылды",
  "video.clearContinuation": "Қалпына келтіру хабарын жабу",
  "generation.title": "Сіздің жұмысыңыз",
  "generation.activeTitle": "Сурет жасалуда",
  "generation.activeBody": "Композиция мен детальдарды жинап жатырмыз. Экранды ашық қалдыруға болады.",
  "generation.cancel": "Жасауды тоқтату",
  "generation.done": "Сурет дайын",
  "generation.doneBody": "Нәтижені сақтаңыз немесе жаңа жұмысты бастаңыз.",
  "generation.failed": "Сурет жасалмады",
  "generation.failedBody": "Кредиттер жоғалмайды. Студияға оралып, қайта көріңіз.",
  "generation.cancelled": "Жасау тоқтатылды",
  "generation.cancelledBody": "Қайтып, жаңа идеяны іске қосуға болады.",
  "generation.download": "Жүктеп алу",
  "generation.repeat": "Қайталау",
  "generation.remix": "Нұсқа жасау",
  "generation.upscale": "2× үлкейту",
  "generation.share": "Бөлісу",
  "generation.sharing": "Файл дайындалуда…",
  "generation.shareFailed": "Жүйелік мәзір ашылмады. Файлды жүктеп алуға болады.",
  "generation.shareUnsupported": "Бұл құрылғыда файлды жүктеп алып, қолмен жіберуге болады.",
  "generation.newWork": "Жаңа жұмыс",
  "generation.resultAlt": "KELBET дайын суреті",
  "generation.refresh": "Сілтемені жаңарту",
  "generation.unavailableTitle": "Жұмыс қолжетімсіз",
  "generation.unavailableBody": "Сілтеменің мерзімі өтуі немесе жұмыстың жойылуы мүмкін. Архивті ашыңыз не жаңасын бастаңыз.",
  "generation.backToHistory": "Жұмыстарымды ашу",
  "generation.createImage": "Сурет жасау",
  "generation.createVideo": "Бейне жасау",
  "generation.routeImage": "KELBET Image",
  "generation.routeVideo": "KELBET Motion",
  "generation.routeUpscale": "KELBET Upscale",
  "generation.details": "Жұмыс деректері",
  "generation.model": "Студия бағыты",
  "generation.price": "Баға",
  "generation.videoTitle": "Сіздің ролигіңіз",
  "generation.videoActiveTitle": "Көрініс түсірілуде",
  "generation.videoActiveBody": "Қозғалысты кадрлар бойынша жинап жатырмыз. Шыға берсеңіз болады — Telegram дайын болғанда хабарлайды.",
  "generation.videoDone": "Бейне дайын",
  "generation.videoDoneBody": "Роликті қарап, жүктеп алыңыз немесе өз фотоңыздан жаңасын жасаңыз.",
  "generation.videoResultAlt": "KELBET дайын бейнесі",
  "generation.makeFromFrame": "Кадрды жандандыру",
  "generation.newPhotoVideo": "Фотодан жаңа бейне",
  "generation.stageQueued": "Көрініс кезекте",
  "generation.stageSubmitting": "Режиссерлік бриф жіберілуде",
  "generation.stageRunning": "Кадрлар бойынша қозғалыс құрылуда",
  "generation.stageFinalizing": "Финалдық ролик жиналуда",
  "generation.etaRemaining": "Шамамен қалды",
  "history.title": "Тарих",
  "history.empty": "Әзірге бос — алғашқы жұмысты жасаңыз",
  "history.eyebrow": "Студия мұрағаты",
  "history.subtitle": "Барлық визуалды тәжірибеңіз бір жерде.",
  "history.ready": "Дайын",
  "history.active": "Жасалуда",
  "history.failed": "Сәтсіз",
  "history.cancelled": "Тоқтатылды",
  "history.noPreview": "Алдын ала көрініс жоқ",
  "history.videoPreview": "Бейне",
  "history.imageWork": "KELBET Image",
  "history.videoWork": "KELBET Motion",
  "history.previewAlt": "KELBET жұмысының алдын ала көрінісі",
  "history.credits": "кр.",
  "history.itemOpen": "Жұмысты ашу",
  "history.filterLabel": "Жұмыстар сүзгісі",
  "history.filterAll": "Барлығы",
  "history.filterImage": "Суреттер",
  "history.filterVideo": "Бейнелер",
  "history.filterActive": "Жұмыста",
  "history.filterEmpty": "Бұл санатта әзірге жұмыс жоқ",
  "plans.title": "Жоспарлар",
  "plans.body": "Telegram Stars қауіпсіз шоты арқылы цифрлық кредит сатып алу.",
  "plans.badge": "Telegram Stars",
  "plans.subtitle": "Баға тапсырыста бекітіледі және шот ашылғаннан кейін өзгермейді.",
  "plans.credits": "кредит",
  "plans.pay": "{stars} ⭐-ға сатып алу",
  "plans.opening": "Шот ашылуда…",
  "plans.recommended": "Ұсынамыз",
  "plans.terms": "Сатып алу және қайтару шарттарын оқыдым және келісемін",
  "plans.openTerms": "Шарттарды ашу",
  "plans.termsAccepted": "Шарттар қабылданды — пакетті таңдауға болады.",
  "plans.termsRequired": "Алдымен сатып алу шарттарын растаңыз.",
  "plans.unavailable": "Шарттар мен қолдауды тексеру аяқталғанша төлем уақытша жабық.",
  "plans.history": "Сатып алу тарихы",
  "plans.emptyHistory": "Әзірге сатып алу жоқ",
  "plans.pending": "Төлем күтілуде",
  "plans.paid": "Төленді",
  "plans.cancelled": "Болдырылмады",
  "plans.invoiceFailed": "Шотты ашу мүмкін болмады. Қайта көріңіз.",
  "profile.title": "Жеке кабинет",
  "profile.eyebrow": "KELBET кеңістігі",
  "profile.subtitle": "Баланс, тіл, хабарламалар және көмек — бір жерде.",
  "profile.anonymous": "KELBET қолданушысы",
  "profile.walletEyebrow": "Кредиттер",
  "profile.walletTitle": "Кредит әмияны",
  "profile.available": "Қолжетімді",
  "profile.topUp": "Толтыру",
  "profile.preferencesEyebrow": "Дербес баптау",
  "profile.preferencesTitle": "Баптаулар",
  "profile.languageHelp": "Интерфейс және бот хабарлары",
  "profile.trustEyebrow": "Сенім және көмек",
  "profile.trustTitle": "Қолдау",
  "profile.support": "Команда көмегі",
  "profile.supportHelp": "Бот чатында команданы жазыңыз",
  "profile.purchases": "Сатып алу және кредит",
  "profile.purchasesHelp": "Пакеттер, мәртебелер және тарих",
  "profile.terms": "Сатып алу шарттары",
  "profile.termsHelp": "Төлем, қайтару және қолдау",
  "profile.language": "Тіл",
  "profile.plan": "Жоспар",
  "profile.balance": "Баланс",
  "profile.reserved": "Резервте",
  "profile.notifications": "Хабарландырулар",
  "profile.readyNotifications": "Нәтиже дайын",
  "profile.readyNotificationsHelp": "Жасау аяқталғанда KELBET Telegram-ға хабарлама жібереді.",
  "profile.notificationUpdateError": "Баптауды сақтау мүмкін болмады. Қайта көріңіз.",
  "common.retry": "Қайталау",
  "common.offline": "Желі жоқ — соңғы деректер көрсетілді",
  "common.error": "Бірдеңе дұрыс болмады",
  "common.loading": "Жүктелуде…",
  "auth.booting": "KELBET ашылуда…",
  "auth.failed": "Telegram арқылы кіру сәтсіз",
  "auth.configurationError":
    "Mini App API мекенжайы қате жиналған. Vercel ішінде Railway-дің нақты URL мекенжайын көрсетіп, Redeploy жасаңыз.",
  "auth.networkError":
    "KELBET серверімен байланыс жоқ. Railway API іске қосылғанын және оның HTTPS мекенжайы Vercel ішінде көрсетілгенін тексеріңіз.",
  "auth.openInTelegram": "KELBET қолданбасын Telegram ішіндегі батырмамен ашыңыз.",
  "auth.unknownError": "Авторизация кезінде белгісіз қате шықты. Қайталап көріңіз.",
};

const catalogs: Record<Language, Record<MessageKey, string>> = { ru, kk };

export function t(lang: Language, key: MessageKey): string {
  return catalogs[lang][key] ?? catalogs.ru[key] ?? key;
}

export type { MessageKey };
