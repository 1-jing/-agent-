#include <functional>

#include <QtCore/QDateTime>
#include <QtCore/QCoreApplication>
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QTimer>
#include <QtCore/QVector>
#include <QtGui/QPainter>
#include <QtGui/QPainterPath>
#include <QtGui/QPixmap>
#include <QtGui/QMouseEvent>
#include <QtNetwork/QNetworkAccessManager>
#include <QtNetwork/QNetworkReply>
#include <QtNetwork/QNetworkRequest>
#include <QtWidgets/QApplication>
#include <QtWidgets/QAbstractItemView>
#include <QtWidgets/QFrame>
#include <QtWidgets/QHeaderView>
#include <QtWidgets/QLabel>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QScrollBar>
#include <QtWidgets/QSlider>
#include <QtWidgets/QTableWidget>
#include <QtWidgets/QWidget>

static QString zh(const wchar_t *text)
{
    return QString::fromWCharArray(text);
}

static QString assetPath(const QString &name)
{
    const QString appDir = QCoreApplication::applicationDirPath();
    const QString cwd = QDir::currentPath();
    const QStringList candidates = {
        appDir + "/" + name,
        appDir + "/assets/" + name,
        cwd + "/" + name,
        cwd + "/assets/" + name,
        QDir(appDir).absoluteFilePath("../" + name),
        QDir(appDir).absoluteFilePath("../assets/" + name),
    };

    for (const QString &path : candidates) {
        if (QFileInfo::exists(path)) {
            return path;
        }
    }
    return name;
}

static QString styleColor(const QColor &color)
{
    return QString("rgba(%1,%2,%3,%4)")
        .arg(color.red())
        .arg(color.green())
        .arg(color.blue())
        .arg(color.alpha());
}

class TrendPlot : public QWidget
{
public:
    explicit TrendPlot(QWidget *parent = nullptr)
        : QWidget(parent)
    {
        setAttribute(Qt::WA_TransparentForMouseEvents);
        setAttribute(Qt::WA_TranslucentBackground);
    }

    void append(double ph, double temp, double co2)
    {
        appendOne(phValues, ph);
        appendOne(tempValues, temp);
        appendOne(co2Values, co2);
        update();
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        p.fillRect(rect(), QColor(0, 0, 0, 0));

        const QRectF axisArea(42, 66, width() - 92, height() - 122);
        const QRectF graph(axisArea.left() + 42, axisArea.top(), axisArea.width() - 42, axisArea.height());
        drawAxes(&p, axisArea, graph);
        drawLegend(&p);

        drawCurve(&p, graph, phValues, QColor(18, 232, 255), 0.0, 14.0);
        drawCurve(&p, graph, tempValues, QColor(255, 197, 38), 0.0, 40.0);
        drawCurve(&p, graph, co2Values, QColor(112, 230, 87), 0.0, 2.0);
    }

private:
    QVector<double> phValues;
    QVector<double> tempValues;
    QVector<double> co2Values;

    static void appendOne(QVector<double> &values, double value)
    {
        values.append(value);
        while (values.size() > 80) {
            values.remove(0);
        }
    }

    void drawAxes(QPainter *p, const QRectF &axisArea, const QRectF &graph)
    {
        QPen axis(QColor(31, 202, 255, 145));
        axis.setWidth(1);
        p->setPen(axis);
        p->drawLine(axisArea.bottomLeft(), axisArea.topLeft());
        p->drawLine(graph.bottomLeft(), graph.topLeft());
        p->drawLine(axisArea.bottomLeft(), axisArea.bottomRight());
        p->drawLine(axisArea.bottomRight(), axisArea.topRight());

        QFont axisFont("Microsoft YaHei", 10);
        p->setFont(axisFont);

        p->setPen(QColor(18, 232, 255, 210));
        p->drawText(QRectF(axisArea.left() - 32, axisArea.top() - 26, 30, 20), Qt::AlignRight | Qt::AlignVCenter, "pH");
        const QStringList phMarks = {"10", "8", "6", "4", "2"};
        for (int i = 0; i < phMarks.size(); ++i) {
            const double y = axisArea.top() + i * (axisArea.height() / double(phMarks.size() - 1));
            p->drawText(QRectF(axisArea.left() - 38, y - 10, 30, 20), Qt::AlignRight | Qt::AlignVCenter, phMarks[i]);
            p->drawLine(QPointF(axisArea.left() - 4, y), QPointF(axisArea.left(), y));
        }

        p->setPen(QColor(255, 197, 38, 220));
        p->drawText(QRectF(graph.left() - 20, axisArea.top() - 26, 92, 20), Qt::AlignLeft | Qt::AlignVCenter, zh(L"\u6e29\u5ea6 (\u2103)"));
        const QStringList tempMarks = {"40", "30", "20", "10", "0"};
        for (int i = 0; i < tempMarks.size(); ++i) {
            const double y = axisArea.top() + i * (axisArea.height() / double(tempMarks.size() - 1));
            p->drawText(QRectF(graph.left() - 32, y - 10, 28, 20), Qt::AlignRight | Qt::AlignVCenter, tempMarks[i]);
            p->drawLine(QPointF(graph.left() - 4, y), QPointF(graph.left(), y));
        }

        p->setPen(QColor(112, 230, 87, 220));
        p->drawText(QRectF(axisArea.right() - 48, axisArea.top() - 26, 58, 20), Qt::AlignRight | Qt::AlignVCenter, "CO2(%)");
        const QStringList co2Marks = {"2.0", "1.5", "1.0", "0.5", "0"};
        for (int i = 0; i < co2Marks.size(); ++i) {
            const double y = axisArea.top() + i * (axisArea.height() / double(co2Marks.size() - 1));
            p->drawText(QRectF(axisArea.right() + 8, y - 10, 44, 20), Qt::AlignLeft | Qt::AlignVCenter, co2Marks[i]);
            p->drawLine(QPointF(axisArea.right(), y), QPointF(axisArea.right() + 4, y));
        }

    }

    void drawLegend(QPainter *p)
    {
        struct Item {
            QColor color;
            QString text;
        };
        const Item items[] = {
            {QColor(18, 232, 255), "pH"},
            {QColor(255, 197, 38), zh(L"\u6e29\u5ea6 (\u2103)")},
            {QColor(112, 230, 87), "CO2(%)"}
        };

        QFont legendFont("Microsoft YaHei", 10);
        p->setFont(legendFont);
        int x = width() / 2 - 135;
        for (const Item &item : items) {
            QPen pen(item.color);
            pen.setWidth(4);
            pen.setCapStyle(Qt::RoundCap);
            p->setPen(pen);
            p->drawLine(QPointF(x, 25), QPointF(x + 24, 25));
            p->setPen(QColor(225, 248, 255, 230));
            p->drawText(QRectF(x + 34, 15, 90, 22), Qt::AlignLeft | Qt::AlignVCenter, item.text);
            x += 116;
        }
    }

    void drawCurve(QPainter *p, const QRectF &plot, const QVector<double> &values, const QColor &color,
                   double minValue, double maxValue)
    {
        if (values.size() < 2) {
            return;
        }

        QPainterPath path;
        const double span = qMax(0.001, maxValue - minValue);
        for (int i = 0; i < values.size(); ++i) {
            const double x = plot.left() + plot.width() * double(i) / double(qMax(1, values.size() - 1));
            const double clamped = qBound(minValue, values[i], maxValue);
            const double y = plot.bottom() - ((clamped - minValue) / span) * plot.height();
            if (i == 0) {
                path.moveTo(x, y);
            } else {
                path.lineTo(x, y);
            }
        }

        QPen glow(color);
        glow.setWidth(5);
        glow.setColor(QColor(color.red(), color.green(), color.blue(), 34));
        p->setPen(glow);
        p->drawPath(path);

        QPen line(color);
        line.setWidth(2);
        p->setPen(line);
        p->drawPath(path);
    }
};

struct PredictionSample
{
    double minute = 0.0;
    double temp = 0.0;
    double ph = 0.0;
    double co2 = 0.0;
};

class PredictionPlot : public QWidget
{
public:
    explicit PredictionPlot(QWidget *parent = nullptr)
        : QWidget(parent)
    {
        setAttribute(Qt::WA_TransparentForMouseEvents);
        setAttribute(Qt::WA_TranslucentBackground);
    }

    void setSeries(const QVector<PredictionSample> &historyRows,
                   const QVector<PredictionSample> &predictionRows,
                   const QVector<PredictionSample> &futureRows,
                   const QString &modeName)
    {
        history = historyRows;
        prediction = predictionRows;
        futureTrue = futureRows;
        mode = modeName;
        update();
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        p.fillRect(rect(), QColor(0, 0, 0, 0));

        const QRectF axisArea(42, 66, width() - 92, height() - 122);
        const QRectF graph(axisArea.left() + 42, axisArea.top(), axisArea.width() - 42, axisArea.height());
        drawAxes(&p, axisArea, graph);
        drawLegend(&p);

        drawChannel(&p, graph, 0, QColor(255, 197, 38), 0.0, 40.0);
        drawChannel(&p, graph, 1, QColor(18, 232, 255), 0.0, 14.0);
        drawChannel(&p, graph, 2, QColor(112, 230, 87), 0.0, 20.0);
    }

private:
    QVector<PredictionSample> history;
    QVector<PredictionSample> prediction;
    QVector<PredictionSample> futureTrue;
    QString mode = zh(L"\u5b9e\u65f6\u9884\u6d4b");

    double channelValue(const PredictionSample &sample, int channel) const
    {
        if (channel == 0) {
            return sample.temp;
        }
        if (channel == 1) {
            return sample.ph;
        }
        return sample.co2;
    }

    QPointF mapPoint(const QRectF &plot, const PredictionSample &sample, int channel,
                     double minValue, double maxValue) const
    {
        const double xSpan = 239.0;
        const double x = plot.left() + ((sample.minute + 179.0) / xSpan) * plot.width();
        const double span = qMax(0.001, maxValue - minValue);
        const double value = qBound(minValue, channelValue(sample, channel), maxValue);
        const double y = plot.bottom() - ((value - minValue) / span) * plot.height();
        return QPointF(x, y);
    }

    void drawAxes(QPainter *p, const QRectF &axisArea, const QRectF &graph)
    {
        QPen axis(QColor(31, 202, 255, 145));
        axis.setWidth(1);
        p->setPen(axis);
        p->drawRect(graph);

        p->setPen(QColor(80, 170, 220, 80));
        for (int i = 1; i < 4; ++i) {
            const double y = graph.top() + i * graph.height() / 4.0;
            p->drawLine(QPointF(graph.left(), y), QPointF(graph.right(), y));
        }
        const QVector<double> marks = {-179.0, -120.0, -60.0, 0.0, 60.0};
        for (double minute : marks) {
            const double x = graph.left() + ((minute + 179.0) / 239.0) * graph.width();
            p->drawLine(QPointF(x, graph.top()), QPointF(x, graph.bottom()));
        }

        p->setFont(QFont("Microsoft YaHei", 10));
        p->setPen(QColor(190, 230, 242, 220));
        p->drawText(QRectF(graph.left(), graph.bottom() + 12, graph.width(), 24),
                    Qt::AlignCenter, zh(L"\u76f8\u5bf9\u5206\u949f  -179 ... +60"));
        p->drawText(QRectF(graph.left(), 14, 180, 24),
                    Qt::AlignLeft | Qt::AlignVCenter, mode);
        p->drawText(QRectF(axisArea.left() - 22, axisArea.top() - 26, 80, 20),
                    Qt::AlignLeft | Qt::AlignVCenter, zh(L"\u5386\u53f2"));
        p->drawText(QRectF(graph.right() - 82, axisArea.top() - 26, 90, 20),
                    Qt::AlignRight | Qt::AlignVCenter, zh(L"\u672a\u6765"));
    }

    void drawLegend(QPainter *p)
    {
        struct Item {
            QColor color;
            QString text;
        };
        const Item items[] = {
            {QColor(255, 197, 38), zh(L"\u6e29\u5ea6")},
            {QColor(18, 232, 255), "pH"},
            {QColor(112, 230, 87), "CO2"},
            {QColor(255, 92, 92), zh(L"\u771f\u5b9e\u672a\u6765")}
        };

        p->setFont(QFont("Microsoft YaHei", 10));
        int x = width() / 2 - 230;
        for (const Item &item : items) {
            QPen pen(item.color);
            pen.setWidth(3);
            pen.setCapStyle(Qt::RoundCap);
            p->setPen(pen);
            p->drawLine(QPointF(x, 25), QPointF(x + 24, 25));
            p->setPen(QColor(225, 248, 255, 230));
            p->drawText(QRectF(x + 32, 15, 96, 22), Qt::AlignLeft | Qt::AlignVCenter, item.text);
            x += 112;
        }
    }

    void drawSeries(QPainter *p, const QRectF &plot, const QVector<PredictionSample> &rows,
                    int channel, const QColor &color, double minValue, double maxValue,
                    Qt::PenStyle style, int width)
    {
        if (rows.size() < 2) {
            return;
        }

        QPainterPath path;
        for (int i = 0; i < rows.size(); ++i) {
            const QPointF point = mapPoint(plot, rows[i], channel, minValue, maxValue);
            if (i == 0) {
                path.moveTo(point);
            } else {
                path.lineTo(point);
            }
        }

        QPen pen(color);
        pen.setWidth(width);
        pen.setStyle(style);
        pen.setCapStyle(Qt::RoundCap);
        pen.setJoinStyle(Qt::RoundJoin);
        p->setPen(pen);
        p->drawPath(path);
    }

    void drawChannel(QPainter *p, const QRectF &plot, int channel, const QColor &color,
                     double minValue, double maxValue)
    {
        drawSeries(p, plot, history, channel, QColor(color.red(), color.green(), color.blue(), 210),
                   minValue, maxValue, Qt::SolidLine, 2);
        drawSeries(p, plot, prediction, channel, QColor(color.red(), color.green(), color.blue(), 235),
                   minValue, maxValue, Qt::DashLine, 2);
        if (!futureTrue.isEmpty()) {
            const QColor trueColor = channel == 0 ? QColor(255, 92, 92, 210)
                                   : channel == 1 ? QColor(255, 132, 132, 190)
                                                  : QColor(255, 166, 92, 190);
            drawSeries(p, plot, futureTrue, channel, trueColor, minValue, maxValue, Qt::SolidLine, 2);
        }
    }
};

class SwitchButton : public QWidget
{
public:
    explicit SwitchButton(QWidget *parent = nullptr)
        : QWidget(parent)
    {
        setCursor(Qt::PointingHandCursor);
        setAttribute(Qt::WA_TranslucentBackground);
    }

    void setChecked(bool value)
    {
        if (checked == value) {
            return;
        }
        checked = value;
        update();
    }

    bool isChecked() const
    {
        return checked;
    }

    std::function<void(bool)> onToggled;

protected:
    void mousePressEvent(QMouseEvent *event) override
    {
        if (event->button() != Qt::LeftButton) {
            return;
        }
        checked = !checked;
        update();
        if (onToggled) {
            onToggled(checked);
        }
    }

    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        const QRectF r = rect().adjusted(1, 1, -1, -1);
        const QColor border = checked ? QColor(38, 243, 209, 230) : QColor(80, 170, 220, 180);
        const QColor bg = checked ? QColor(0, 142, 132, 255) : QColor(8, 35, 60, 255);
        p.setPen(QPen(border, 1.6));
        p.setBrush(bg);
        p.drawRoundedRect(r, r.height() / 2.0, r.height() / 2.0);

        const qreal knob = r.height() - 8;
        const qreal x = checked ? r.right() - knob - 4 : r.left() + 4;
        QRectF k(x, r.top() + 4, knob, knob);
        p.setPen(Qt::NoPen);
        p.setBrush(checked ? QColor(38, 243, 209, 235) : QColor(92, 137, 176, 230));
        p.drawEllipse(k);

        p.setPen(checked ? QColor(222, 255, 250, 235) : QColor(135, 170, 198, 210));
        p.setFont(QFont("Microsoft YaHei", 12, QFont::Bold));
        p.drawText(r.adjusted(checked ? 10 : 30, 0, checked ? -30 : -10, 0),
                   Qt::AlignCenter, checked ? "ON" : "OFF");
    }

private:
    bool checked = false;
};

class ControlWindow : public QWidget
{
public:
    explicit ControlWindow(const QString &baseUrl, QWidget *parent = nullptr)
        : QWidget(parent),
          apiBase(baseUrl),
          network(new QNetworkAccessManager(this)),
          background(assetPath("control_background_final_1920x1080.png"))
    {
        setWindowTitle(zh(L"\u667a\u80fd\u53d1\u9175\u7f50\u63a7\u5236\u7aef"));
        setFixedSize(1920, 1080);
        setAutoFillBackground(false);
        setStyleSheet(globalStyle());

        buildMetrics();
        buildNodeStatus();
        buildTrendAndStage();
        buildAiAndTables();
        buildControls();

        connect(&pollTimer, &QTimer::timeout, this, [this]() { pollLatest(); });
        pollTimer.start(2000);
        pollLatest();

        connect(&realPredictTimer, &QTimer::timeout, this, [this]() {
            if (!offlineDemoMode) {
                requestRealPrediction();
            }
        });
        realPredictTimer.start(60000);

        connect(&demoTimer, &QTimer::timeout, this, [this]() { requestDemoNext(); });

        QTimer::singleShot(3000, this, [this]() {
            requestRealPrediction();
        });
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        if (!background.isNull()) {
            p.drawPixmap(rect(), background);
        } else {
            p.fillRect(rect(), QColor(0, 16, 35));
            p.setPen(QColor(0, 180, 255));
            p.drawText(rect(), Qt::AlignCenter, "control_background_final_1920x1080.png missing");
        }
    }

private:
    QString apiBase;
    QNetworkAccessManager *network;
    QTimer pollTimer;
    QTimer realPredictTimer;
    QTimer demoTimer;
    QPixmap background;

    QLabel *phValue = nullptr;
    QLabel *tempValue = nullptr;
    QLabel *co2Value = nullptr;
    QLabel *waterValue = nullptr;
    QLabel *nodeRows[5] = {};
    QLabel *nodeDetailRows[5] = {};
    QLabel *stageTitles[4] = {};
    QLabel *stageIndicators[4] = {};
    QLabel *decisionText = nullptr;
    QLabel *actionText = nullptr;
    QLabel *actionSubText = nullptr;
    QLabel *queuedActionText = nullptr;
    QLabel *priorityText = nullptr;
    QLabel *motorState = nullptr;
    QLabel *motorRpmState = nullptr;
    QLabel *motorHealthState = nullptr;
    QLabel *servoState = nullptr;
    QLabel *servoHealthState = nullptr;
    QLabel *pumpState = nullptr;
    QLabel *pumpHealthState = nullptr;
    QLabel *queueState = nullptr;
    QLabel *predictionModeText = nullptr;
    QLabel *predictionRiskText = nullptr;
    QLabel *predictionChannelsText = nullptr;
    QLabel *predictionLeadText = nullptr;
    QLabel *predictionMaxZText = nullptr;
    QLabel *predictionConfidenceText = nullptr;
    QLabel *predictionReasonText = nullptr;
    QLabel *motorCommandValue = nullptr;
    QLabel *servoCommandValue = nullptr;
    QLabel *connectionState = nullptr;
    QTableWidget *eventTable = nullptr;
    TrendPlot *trendPlot = nullptr;
    PredictionPlot *predictionPlot = nullptr;
    QPlainTextEdit *feedbackLog = nullptr;
    QSlider *motorSlider = nullptr;
    QSlider *servoSlider = nullptr;
    SwitchButton *pumpSwitch = nullptr;
    QString localPendingAction;
    bool updatingFromTelemetry = false;
    bool offlineDemoMode = false;

    QString globalStyle() const
    {
        return QString(
            "QWidget {"
            "  background: transparent;"
            "  color: #dff8ff;"
            "  font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;"
            "}"
            "QLabel { background: transparent; }"
            "QPushButton {"
            "  color: #dff8ff;"
            "  background-color: rgba(0, 42, 72, 92);"
            "  border: 1px solid rgba(0, 190, 255, 175);"
            "  border-radius: 6px;"
            "  padding: 4px 8px;"
            "  font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: rgba(0, 112, 160, 120); }"
            "QPushButton:pressed { background-color: rgba(0, 210, 255, 80); }"
            "QSlider::groove:horizontal {"
            "  height: 6px;"
            "  background: rgba(0, 92, 138, 150);"
            "  border-radius: 3px;"
            "}"
            "QSlider::sub-page:horizontal {"
            "  background: rgba(38, 243, 209, 220);"
            "  border-radius: 3px;"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 18px; height: 18px;"
            "  margin: -7px 0;"
            "  border-radius: 9px;"
            "  background: #26f3d1;"
            "  border: 1px solid rgba(210, 255, 255, 210);"
            "}"
            "QCheckBox { spacing: 8px; color: #dff8ff; font-weight: 600; }"
            "QCheckBox::indicator { width: 78px; height: 38px; }"
            "QCheckBox::indicator:unchecked {"
            "  image: none;"
            "  border: 1px solid rgba(80, 170, 220, 180);"
            "  border-radius: 19px;"
            "  background: rgba(8, 35, 60, 180);"
            "}"
            "QCheckBox::indicator:checked {"
            "  image: none;"
            "  border: 1px solid rgba(38, 243, 209, 230);"
            "  border-radius: 19px;"
            "  background: rgba(0, 170, 150, 170);"
            "}"
            "QPlainTextEdit, QTableWidget {"
            "  background: rgba(0, 22, 42, 55);"
            "  border: 0;"
            "  color: #bfefff;"
            "  selection-background-color: rgba(0, 170, 220, 130);"
            "}"
            "QHeaderView::section {"
            "  background: rgba(0, 58, 96, 128);"
            "  color: #9eeeff;"
            "  border: 0;"
            "  padding: 3px;"
            "}"
        );
    }

    QLabel *label(const QString &text, const QRect &rect, int pointSize,
                  const QColor &color = QColor(220, 248, 255), int weight = QFont::Normal,
                  Qt::Alignment alignment = Qt::AlignLeft | Qt::AlignVCenter)
    {
        QLabel *w = new QLabel(text, this);
        w->setGeometry(rect);
        QFont f("Microsoft YaHei", pointSize, weight);
        w->setFont(f);
        w->setAlignment(alignment);
        w->setStyleSheet(QString("color: %1; background: transparent;").arg(styleColor(color)));
        return w;
    }

    QLabel *wrapLabel(const QString &text, const QRect &rect, int pointSize,
                      const QColor &color, int weight = QFont::Normal,
                      Qt::Alignment alignment = Qt::AlignLeft | Qt::AlignVCenter)
    {
        QLabel *w = label(text, rect, pointSize, color, weight, alignment);
        w->setWordWrap(true);
        return w;
    }

    QLabel *valueLabel(const QRect &rect, const QString &text = "--")
    {
        QLabel *w = label(text, rect, 24, QColor(38, 243, 209), QFont::Bold, Qt::AlignCenter);
        w->setStyleSheet("color: #26f3d1; background: transparent; font-weight: 700;");
        return w;
    }

    QPushButton *button(const QString &text, const QRect &rect)
    {
        QPushButton *b = new QPushButton(text, this);
        b->setGeometry(rect);
        b->setCursor(Qt::PointingHandCursor);
        return b;
    }

    void buildMetrics()
    {
        label("pH", QRect(80, 176, 130, 26), 13, QColor(225, 248, 255), QFont::Bold);
        phValue = valueLabel(QRect(58, 206, 152, 52));

        label(zh(L"\u6e29\u5ea6 (\u2103)"), QRect(308, 176, 140, 26), 13, QColor(225, 248, 255), QFont::Bold);
        tempValue = valueLabel(QRect(286, 206, 152, 52));

        label(zh(L"\u6c34\u4f4d (\u7b49\u7ea7)"), QRect(80, 312, 140, 26), 13, QColor(225, 248, 255), QFont::Bold);
        waterValue = valueLabel(QRect(58, 342, 152, 52));

        label("CO2 (%)", QRect(308, 312, 140, 26), 13, QColor(225, 248, 255), QFont::Bold);
        co2Value = valueLabel(QRect(286, 342, 152, 52));
    }

    void buildNodeStatus()
    {
        const QStringList names = {
            zh(L"2K0300 \u8282\u70b9"),
            zh(L"HTTP \u4e0a\u4f20"),
            zh(L"SQLite \u5b58\u50a8"),
            zh(L"LLM \u63a8\u7406"),
            zh(L"\u6267\u884c\u5668\u63a7\u5236")
        };

        for (int i = 0; i < names.size(); ++i) {
            const int y = 502 + i * 48;
            label(names[i], QRect(78, y, 150, 28), 12, QColor(210, 236, 245));
            nodeRows[i] = label(zh(L"\u7b49\u5f85"), QRect(238, y, 72, 28), 12,
                                QColor(150, 205, 235), QFont::Bold, Qt::AlignCenter);
            nodeDetailRows[i] = label("--", QRect(322, y, 126, 28), 12,
                                      QColor(105, 205, 230), QFont::Normal, Qt::AlignRight | Qt::AlignVCenter);
        }
    }

    void buildTrendAndStage()
    {
        trendPlot = new TrendPlot(this);
        trendPlot->setGeometry(510, 116, 820, 430);
        predictionPlot = new PredictionPlot(this);
        predictionPlot->setGeometry(510, 116, 820, 430);

        const QStringList stages = {
            QString("Stage 1\n") + zh(L"\u542f\u52a8\u671f"),
            QString("Stage 2\n") + zh(L"\u6307\u6570\u671f"),
            QString("Stage 3\n") + zh(L"\u7a33\u5b9a\u671f"),
            QString("Stage 4\n") + zh(L"\u8870\u9000\u671f")
        };
        const int xs[] = {532, 742, 954, 1162};
        for (int i = 0; i < 4; ++i) {
            stageTitles[i] = label(stages[i], QRect(xs[i], 642, 126, 54), 12, QColor(210, 245, 255),
                                   QFont::Bold, Qt::AlignCenter);
            stageIndicators[i] = label(zh(L"\u25cb"), QRect(xs[i], 704, 126, 28), 21,
                                       QColor(105, 150, 175), QFont::Bold, Qt::AlignCenter);
        }
        setStage(0);
    }

    void buildAiAndTables()
    {
        label(zh(L"\u9636\u6bb5\u8bca\u65ad"), QRect(1400, 164, 120, 22), 10, QColor(190, 220, 235));
        label(zh(L"\u5efa\u8bae\u52a8\u4f5c"), QRect(1640, 164, 120, 22), 10, QColor(190, 220, 235));
        decisionText = wrapLabel(zh(L"\u7b49\u5f85\u6570\u636e"), QRect(1388, 196, 218, 48), 14,
                                 QColor(255, 210, 60), QFont::Bold, Qt::AlignCenter);
        actionText = wrapLabel(zh(L"\u7b49\u5f85\u63a8\u7406"), QRect(1628, 194, 224, 42), 13,
                               QColor(128, 235, 112), QFont::Bold, Qt::AlignCenter);
        actionSubText = wrapLabel(zh(L"\u4fdd\u6301\u5f53\u524d\u63a7\u5236\u7b56\u7565"), QRect(1640, 242, 198, 28), 9,
                                  QColor(165, 195, 210), QFont::Normal, Qt::AlignCenter);
        label(zh(L"\u5df2\u6392\u961f\u52a8\u4f5c"), QRect(1400, 306, 128, 24), 12, QColor(210, 236, 245));
        queuedActionText = label(zh(L"\u6682\u65e0\u6307\u4ee4"), QRect(1420, 334, 218, 28), 13,
                                 QColor(38, 243, 209), QFont::Bold, Qt::AlignCenter);
        priorityText = label(zh(L"\u4f18\u5148\u7ea7: \u4e2d"), QRect(1728, 335, 124, 30), 12,
                             QColor(210, 236, 245), QFont::Normal, Qt::AlignCenter);
        connectionState = label("", QRect(0, 0, 1, 1), 1, QColor(155, 220, 245));

        predictionModeText = label(zh(L"\u5f53\u524d\u6a21\u5f0f: \u5b9e\u65f6\u9884\u6d4b"), QRect(1382, 382, 210, 22), 10,
                                   QColor(210, 236, 245), QFont::Bold);
        predictionRiskText = label("NORMAL", QRect(1596, 382, 104, 22), 12,
                                   QColor(112, 230, 87), QFont::Bold, Qt::AlignCenter);
        connect(button(zh(L"\u79bb\u7ebf\u6570\u636e\u5c55\u793a"), QRect(1710, 378, 142, 30)), &QPushButton::clicked,
                this, [this]() { startOfflineDemo(); });
        predictionChannelsText = label(zh(L"\u5f02\u5e38\u901a\u9053: -"), QRect(1382, 410, 170, 22), 10,
                                       QColor(210, 236, 245));
        predictionLeadText = label("lead_minutes: -", QRect(1554, 410, 146, 22), 10,
                                   QColor(210, 236, 245));
        predictionMaxZText = label("max_z: -", QRect(1710, 410, 142, 22), 10,
                                   QColor(210, 236, 245));
        predictionConfidenceText = label(zh(L"\u9884\u6d4b\u53ef\u4fe1\u5ea6: --"), QRect(1382, 436, 212, 22), 10,
                                         QColor(255, 176, 42), QFont::Bold);
        predictionReasonText = wrapLabel(zh(L"\u7b49\u5f85\u9884\u6d4b\u7ed3\u679c"), QRect(1596, 432, 262, 34), 8,
                                         QColor(165, 195, 210));

        label(zh(L"\u7535\u673a\u6405\u62cc"), QRect(1368, 462, 100, 20), 10, QColor(225, 248, 255), QFont::Normal, Qt::AlignCenter);
        label(zh(L"\u8235\u673a\u89d2\u5ea6"), QRect(1500, 462, 100, 20), 10, QColor(225, 248, 255), QFont::Normal, Qt::AlignCenter);
        label(zh(L"\u6c34\u6cf5\u5f00\u5173"), QRect(1634, 462, 100, 20), 10, QColor(225, 248, 255), QFont::Normal, Qt::AlignCenter);
        label(zh(L"\u52a8\u4f5c\u961f\u5217"), QRect(1766, 462, 100, 20), 10, QColor(225, 248, 255), QFont::Normal, Qt::AlignCenter);
        motorState = label("--", QRect(1368, 492, 100, 22), 13, QColor(38, 243, 209),
                           QFont::Bold, Qt::AlignCenter);
        motorRpmState = label("--", QRect(1368, 514, 100, 18), 9, QColor(190, 220, 235),
                              QFont::Normal, Qt::AlignCenter);
        motorHealthState = label("", QRect(1368, 532, 100, 18), 9, QColor(112, 230, 87),
                                 QFont::Normal, Qt::AlignCenter);
        servoState = label("--", QRect(1500, 498, 100, 24), 15, QColor(38, 243, 209),
                           QFont::Bold, Qt::AlignCenter);
        servoHealthState = label("", QRect(1500, 532, 100, 18), 9, QColor(112, 230, 87),
                                 QFont::Normal, Qt::AlignCenter);
        pumpState = label("--", QRect(1634, 498, 100, 24), 15, QColor(38, 243, 209),
                          QFont::Bold, Qt::AlignCenter);
        pumpHealthState = label("", QRect(1634, 532, 100, 18), 9, QColor(112, 230, 87),
                                QFont::Normal, Qt::AlignCenter);
        queueState = wrapLabel(zh(L"\u7b49\u5f85\u6267\u884c"), QRect(1766, 498, 100, 38), 10, QColor(155, 220, 245),
                               QFont::Bold, Qt::AlignCenter);

        eventTable = new QTableWidget(0, 5, this);
        eventTable->setGeometry(1362, 654, 524, 96);
        eventTable->setHorizontalHeaderLabels({zh(L"\u65f6\u95f4"), zh(L"\u7b49\u7ea7"), zh(L"\u5f02\u5e38\u7c7b\u578b"), zh(L"\u63cf\u8ff0"), zh(L"\u72b6\u6001")});
        eventTable->verticalHeader()->setVisible(false);
        eventTable->horizontalHeader()->setVisible(false);
        eventTable->setColumnWidth(0, 78);
        eventTable->setColumnWidth(1, 78);
        eventTable->setColumnWidth(2, 116);
        eventTable->setColumnWidth(3, 164);
        eventTable->setColumnWidth(4, 88);
        eventTable->verticalHeader()->setDefaultSectionSize(28);
        eventTable->setShowGrid(false);
        eventTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
        eventTable->setSelectionMode(QAbstractItemView::NoSelection);
        eventTable->setFocusPolicy(Qt::NoFocus);
        eventTable->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        eventTable->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        eventTable->setFrameShape(QFrame::NoFrame);
        eventTable->viewport()->setStyleSheet("background: transparent;");
    }

    void buildControls()
    {
        motorCommandValue = label("0%", QRect(104, 890, 90, 32), 18, QColor(38, 243, 209),
                                  QFont::Bold, Qt::AlignLeft | Qt::AlignVCenter);
        motorSlider = new QSlider(Qt::Horizontal, this);
        motorSlider->setGeometry(92, 944, 300, 30);
        motorSlider->setRange(0, 100);
        motorSlider->setSingleStep(10);
        motorSlider->setPageStep(10);
        motorSlider->setTickInterval(10);
        motorSlider->setValue(0);
        connect(motorSlider, &QSlider::valueChanged, this, [this](int value) {
            const int rounded = (value / 10) * 10;
            if (rounded != value) {
                motorSlider->setValue(rounded);
                return;
            }
            motorCommandValue->setText(QString("%1%").arg(rounded));
        });
        connect(motorSlider, &QSlider::sliderReleased, this, [this]() {
            sendAction(QString("motor_pwm_%1").arg(motorSlider->value()));
        });
        connect(button(zh(L"\u505c\u6b62"), QRect(342, 890, 70, 30)), &QPushButton::clicked,
                this, [this]() { motorSlider->setValue(0); sendAction("motor_stop"); });

        pumpSwitch = new SwitchButton(this);
        pumpSwitch->setGeometry(670, 916, 126, 50);
        pumpSwitch->onToggled = [this](bool checked) {
            if (updatingFromTelemetry) {
                return;
            }
            sendAction(checked ? "pump_water_on" : "pump_water_off");
        };
        servoCommandValue = label("0deg", QRect(1070, 890, 110, 32), 18, QColor(38, 243, 209),
                                  QFont::Bold, Qt::AlignLeft | Qt::AlignVCenter);
        servoSlider = new QSlider(Qt::Horizontal, this);
        servoSlider->setGeometry(1040, 944, 300, 30);
        servoSlider->setRange(0, 180);
        servoSlider->setSingleStep(5);
        servoSlider->setPageStep(15);
        connect(servoSlider, &QSlider::valueChanged, this, [this](int value) {
            servoCommandValue->setText(QString("%1deg").arg(value));
        });
        connect(servoSlider, &QSlider::sliderReleased, this, [this]() {
            sendAction(QString("vent_angle_%1").arg(servoSlider->value()));
        });
        connect(button("0", QRect(1210, 890, 46, 30)), &QPushButton::clicked,
                this, [this]() { servoSlider->setValue(0); sendAction("vent_angle_0"); });
        connect(button("45", QRect(1264, 890, 46, 30)), &QPushButton::clicked,
                this, [this]() { servoSlider->setValue(45); sendAction("vent_angle_45"); });
        connect(button("90", QRect(1318, 890, 46, 30)), &QPushButton::clicked,
                this, [this]() { servoSlider->setValue(90); sendAction("vent_angle_90"); });

        feedbackLog = new QPlainTextEdit(this);
        feedbackLog->setGeometry(1510, 892, 318, 108);
        feedbackLog->setReadOnly(true);
        feedbackLog->setFrameShape(QFrame::NoFrame);
        feedbackLog->setPlainText(zh(L"\u7b49\u5f85\u6307\u4ee4"));
    }

    void pollLatest()
    {
        QNetworkRequest request(QUrl(apiBase + "/latest"));
        QNetworkReply *reply = network->get(request);
        connect(reply, &QNetworkReply::finished, this, [this, reply]() {
            const QByteArray body = reply->readAll();
            if (reply->error() != QNetworkReply::NoError) {
                setOnline(false, reply->errorString());
                reply->deleteLater();
                return;
            }

            const QJsonDocument doc = QJsonDocument::fromJson(body);
            if (!doc.isObject()) {
                setOnline(false, "bad json");
                reply->deleteLater();
                return;
            }

            applyTelemetry(doc.object());
            reply->deleteLater();
        });
    }

    void sendAction(const QString &action)
    {
        localPendingAction = action;
        QJsonObject payload;
        payload["device_id"] = "2k0300-fermenter-node";
        payload["action"] = action;

        QNetworkRequest request(QUrl(apiBase + "/queue_action"));
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        QNetworkReply *reply = network->post(request, QJsonDocument(payload).toJson(QJsonDocument::Compact));
        appendLog(zh(L"\u4e0b\u53d1: ") + action);

        connect(reply, &QNetworkReply::finished, this, [this, reply, action]() {
            const QByteArray body = reply->readAll();
            if (reply->error() != QNetworkReply::NoError) {
                appendLog(zh(L"\u5931\u8d25: ") + reply->errorString());
                connectionState->setText(zh(L"\u63a5\u53e3: \u4e0b\u53d1\u5931\u8d25"));
            } else {
                const QJsonDocument doc = QJsonDocument::fromJson(body);
                const bool ok = doc.isObject() && doc.object().value("ok").toBool(false);
                if (!ok && localPendingAction == action) {
                    localPendingAction.clear();
                }
                appendLog((ok ? zh(L"\u5df2\u5165\u961f: ") : zh(L"\u88ab\u62d2\u7edd: ")) + action);
                queueState->setText(ok ? zh(L"\u5df2\u5165\u961f") : zh(L"\u62d2\u7edd"));
            }
            reply->deleteLater();
        });
    }

    void requestRealPrediction()
    {
        if (offlineDemoMode) {
            return;
        }
        QNetworkRequest request(QUrl(apiBase + "/predict_real"));
        QNetworkReply *reply = network->get(request);
        connect(reply, &QNetworkReply::finished, this, [this, reply]() {
            const QByteArray body = reply->readAll();
            if (reply->error() != QNetworkReply::NoError) {
                showPredictionMessage(zh(L"\u5f53\u524d\u6a21\u5f0f: \u5b9e\u65f6\u9884\u6d4b"), reply->errorString(), QColor(255, 176, 42));
                reply->deleteLater();
                return;
            }

            const QJsonDocument doc = QJsonDocument::fromJson(body);
            if (!doc.isObject()) {
                showPredictionMessage(zh(L"\u5f53\u524d\u6a21\u5f0f: \u5b9e\u65f6\u9884\u6d4b"), "bad json", QColor(255, 176, 42));
                reply->deleteLater();
                return;
            }

            applyPredictionResult(doc.object());
            reply->deleteLater();
        });
    }

    void startOfflineDemo()
    {
        offlineDemoMode = true;
        realPredictTimer.stop();
        demoTimer.stop();
        showPredictionMessage(zh(L"\u5f53\u524d\u6a21\u5f0f: \u79bb\u7ebf\u6837\u672c\u6f14\u793a"), zh(L"\u6b63\u5728\u51c6\u5907\u79bb\u7ebf\u6837\u672c"), QColor(38, 243, 209));

        QNetworkRequest request(QUrl(apiBase + "/demo_start"));
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
        QNetworkReply *reply = network->post(request, QByteArray("{}"));
        connect(reply, &QNetworkReply::finished, this, [this, reply]() {
            const QByteArray body = reply->readAll();
            const QJsonDocument doc = QJsonDocument::fromJson(body);
            const bool ok = reply->error() == QNetworkReply::NoError && doc.isObject() && doc.object().value("ok").toBool(false);
            if (!ok) {
                const QString reason = doc.isObject() ? doc.object().value("reason").toString(reply->errorString()) : reply->errorString();
                demoTimer.stop();
                offlineDemoMode = false;
                realPredictTimer.start(60000);
                showPredictionMessage(zh(L"\u5f53\u524d\u6a21\u5f0f: \u5b9e\u65f6\u9884\u6d4b"), reason, QColor(255, 176, 42));
                reply->deleteLater();
                return;
            }

            requestDemoNext();
            demoTimer.start(2000);
            reply->deleteLater();
        });
    }

    void requestDemoNext()
    {
        QNetworkRequest request(QUrl(apiBase + "/demo_next"));
        QNetworkReply *reply = network->get(request);
        connect(reply, &QNetworkReply::finished, this, [this, reply]() {
            const QByteArray body = reply->readAll();
            const QJsonDocument doc = QJsonDocument::fromJson(body);
            if (reply->error() != QNetworkReply::NoError || !doc.isObject()) {
                const QString reason = reply->error() != QNetworkReply::NoError ? reply->errorString() : "bad json";
                stopDemoAndResumeReal(reason);
                reply->deleteLater();
                return;
            }

            const QJsonObject obj = doc.object();
            if (!obj.value("ok").toBool(false) && obj.value("finished").toBool(false)) {
                stopDemoAndResumeReal(zh(L"\u79bb\u7ebf\u6837\u672c\u64ad\u653e\u5b8c\u6210"));
                reply->deleteLater();
                return;
            }
            if (!obj.value("ok").toBool(false)) {
                stopDemoAndResumeReal(obj.value("reason").toString(zh(L"\u79bb\u7ebf\u9884\u6d4b\u5931\u8d25")));
                reply->deleteLater();
                return;
            }

            applyPredictionResult(obj);
            reply->deleteLater();
        });
    }

    void stopDemoAndResumeReal(const QString &message)
    {
        demoTimer.stop();
        offlineDemoMode = false;
        realPredictTimer.start(60000);
        showPredictionMessage(zh(L"\u5f53\u524d\u6a21\u5f0f: \u5b9e\u65f6\u9884\u6d4b"), message, QColor(38, 243, 209));
        requestRealPrediction();
    }

    QVector<PredictionSample> parsePredictionRows(const QJsonArray &array) const
    {
        QVector<PredictionSample> rows;
        rows.reserve(array.size());
        for (const QJsonValue &value : array) {
            const QJsonObject row = value.toObject();
            PredictionSample sample;
            sample.minute = row.value("rel_minute").toDouble(0.0);
            sample.temp = row.value("temp").toDouble(0.0);
            sample.ph = row.value("ph").toDouble(0.0);
            sample.co2 = row.value("co2").toDouble(0.0);
            rows.append(sample);
        }
        return rows;
    }

    void applyPredictionResult(const QJsonObject &obj)
    {
        const QString mode = obj.value("mode").toString("real");
        const QString modeText = mode == "demo" ? zh(L"\u5f53\u524d\u6a21\u5f0f: \u79bb\u7ebf\u6837\u672c\u6f14\u793a")
                                                : zh(L"\u5f53\u524d\u6a21\u5f0f: \u5b9e\u65f6\u9884\u6d4b");

        if (!obj.value("ok").toBool(false)) {
            showPredictionMessage(modeText, obj.value("reason").toString(zh(L"\u9884\u6d4b\u6682\u4e0d\u53ef\u7528")), QColor(255, 176, 42));
            return;
        }

        const QVector<PredictionSample> historyRows = parsePredictionRows(obj.value("history").toArray());
        const QVector<PredictionSample> predictionRows = parsePredictionRows(obj.value("prediction").toArray());
        const QVector<PredictionSample> futureRows = parsePredictionRows(obj.value("future_true").toArray());
        if (predictionPlot) {
            predictionPlot->setSeries(historyRows, predictionRows, futureRows,
                                      mode == "demo" ? zh(L"\u79bb\u7ebf\u6837\u672c\u6f14\u793a") : zh(L"\u5b9e\u65f6\u9884\u6d4b"));
        }

        const QString risk = obj.value("risk").toString("normal").toUpper();
        const QString channels = obj.value("channels").toString("-");
        const int lead = obj.value("lead_minutes").toInt(-1);
        const double maxZ = obj.value("max_z").toDouble(0.0);
        const double confidence = obj.value("confidence_score").toDouble(0.0);
        const QString confidenceLevel = obj.value("confidence_level").toString("low");
        const QString reason = obj.value("confidence_reason").toString();

        predictionModeText->setText(modeText);
        predictionRiskText->setText(risk);
        predictionRiskText->setStyleSheet(QString("color: %1; background: transparent; font-weight: 700;")
                                              .arg(styleColor(riskColor(risk.toLower()))));
        predictionChannelsText->setText(zh(L"\u5f02\u5e38\u901a\u9053: ") + channels);
        const QString leadText = lead < 0 ? QString("-") : QString::number(lead);
        predictionLeadText->setText(QString("lead_minutes: %1").arg(leadText));
        predictionMaxZText->setText(QString("max_z: %1").arg(maxZ, 0, 'f', 2));
        predictionConfidenceText->setText(zh(L"\u9884\u6d4b\u53ef\u4fe1\u5ea6: ") + confidenceText(confidenceLevel, confidence));
        predictionConfidenceText->setStyleSheet(QString("color: %1; background: transparent; font-weight: 700;")
                                                    .arg(styleColor(confidenceColor(confidenceLevel))));
        predictionReasonText->setText(reason.isEmpty() ? zh(L"\u9884\u6d4b\u7ed3\u679c\u5df2\u66f4\u65b0") : reason);
    }

    void showPredictionMessage(const QString &modeText, const QString &message, const QColor &color)
    {
        if (predictionModeText) {
            predictionModeText->setText(modeText);
        }
        if (predictionRiskText) {
            predictionRiskText->setText("--");
            predictionRiskText->setStyleSheet(QString("color: %1; background: transparent; font-weight: 700;").arg(styleColor(color)));
        }
        if (predictionChannelsText) {
            predictionChannelsText->setText(zh(L"\u5f02\u5e38\u901a\u9053: -"));
        }
        if (predictionLeadText) {
            predictionLeadText->setText("lead_minutes: -");
        }
        if (predictionMaxZText) {
            predictionMaxZText->setText("max_z: -");
        }
        if (predictionConfidenceText) {
            predictionConfidenceText->setText(zh(L"\u9884\u6d4b\u53ef\u4fe1\u5ea6: --"));
            predictionConfidenceText->setStyleSheet(QString("color: %1; background: transparent; font-weight: 700;").arg(styleColor(color)));
        }
        if (predictionReasonText) {
            predictionReasonText->setText(message);
        }
    }

    QColor riskColor(const QString &risk) const
    {
        if (risk == "warning") {
            return QColor(255, 92, 92);
        }
        if (risk == "watch") {
            return QColor(255, 197, 38);
        }
        return QColor(112, 230, 87);
    }

    QColor confidenceColor(const QString &level) const
    {
        if (level == "high") {
            return QColor(112, 230, 87);
        }
        if (level == "medium" || level == "medium-low") {
            return QColor(255, 197, 38);
        }
        return QColor(255, 92, 92);
    }

    QString confidenceText(const QString &level, double score) const
    {
        QString levelText = zh(L"\u4f4e");
        if (level == "high") {
            levelText = zh(L"\u9ad8");
        } else if (level == "medium" || level == "medium-low") {
            levelText = zh(L"\u4e2d\u4f4e");
        }
        return QString("%1 %2%").arg(levelText).arg(int(score * 100.0 + 0.5));
    }

    void applyTelemetry(const QJsonObject &obj)
    {
        const QString status = obj.value("status").toString();
        const bool online = (status == "online");
        setOnline(online, status);

        const double ph = obj.value("ph_val").toDouble(0.0);
        const double temp = obj.value("temp_c").toDouble(obj.value("tem").toDouble(0.0));
        const double co2 = obj.value("co2_percent").toDouble(0.0);
        const int waterLevel = obj.value("water_level").toInt(0);
        const double motorPwm = obj.value("motor_pwm").toDouble(0.0);
        const double rpm = obj.value("motor_actual_rpm").toDouble(0.0);
        const int ventAngle = int(obj.value("vent_angle").toDouble(0.0));
        const bool pumpEnabled = obj.value("pump_water_enable").toInt(0) != 0;
        const QString fault = obj.value("motor_fault").toString("none");
        const QString alarm = obj.value("alarm_reason").toString("none");
        const QString level = obj.value("alarm_level").toString("normal");
        const QString fallbackAction = obj.value("action").toString("none");
        const QString serverQueuedAction = obj.value("queued_action").toString(
            obj.value("pending_action").toString(fallbackAction));
        QString queuedAction = serverQueuedAction;
        if ((queuedAction == "none" || queuedAction == "keep") && !localPendingAction.isEmpty()) {
            queuedAction = localPendingAction;
        }
        const QString eventAction = obj.value("event_action").toString(fallbackAction);
        const QString priority = obj.value("priority").toString(obj.value("action_priority").toString(zh(L"\u4e2d")));
        const QString recommendation = obj.value("recommendation").toString(
            obj.value("suggestion").toString(obj.value("llm_action").toString(eventAction)));
        const QString diagnosis = obj.value("diagnosis").toString(
            obj.value("stage_diagnosis").toString(obj.value("llm_decision").toString(level)));
        const int stageIndex = stageIndexFromTelemetry(obj);
        const bool actionDone = actionMatchesFeedback(queuedAction, motorPwm, ventAngle, pumpEnabled);
        if (actionDone && queuedAction == localPendingAction) {
            localPendingAction.clear();
        }
        const bool hasQueuedAction = queuedAction != "none" && queuedAction != "keep" && !actionDone;
        const bool motorCommandPending = hasQueuedAction && (queuedAction == "motor_stop" || queuedAction.startsWith("motor_pwm_"));
        const bool servoCommandPending = hasQueuedAction && (queuedAction.startsWith("vent_") || queuedAction.startsWith("vent_angle_"));
        const bool pumpCommandPending = hasQueuedAction && queuedAction.startsWith("pump_water_");
        const int motorTarget = motorTargetFromAction(queuedAction, int(motorPwm / 10.0) * 10);
        const int servoTarget = servoTargetFromAction(queuedAction, ventAngle);
        const int pumpTarget = pumpTargetFromAction(queuedAction);

        phValue->setText(QString::number(ph, 'f', 2));
        tempValue->setText(QString::number(temp, 'f', 1));
        waterValue->setText(QString("%1/4").arg(waterLevel));
        co2Value->setText(QString::number(co2, 'f', 3));
        setStage(stageIndex);

        trendPlot->append(ph, temp, co2);
        motorState->setText(QString::number(rpm, 'f', 1) + " rpm");
        motorState->setStyleSheet(QString("color: %1; background: transparent; font-weight: 700;").arg(
            styleColor(fault == "none" ? QColor(38, 243, 209) : QColor(255, 176, 42))));
        motorRpmState->setText(QString("PWM %1%").arg(int(motorPwm)));
        motorHealthState->setText("");
        motorHealthState->setStyleSheet(QString("color: %1; background: transparent;").arg(
            styleColor(fault == "none" ? QColor(112, 230, 87) : QColor(255, 176, 42))));
        servoState->setText(QString("%1").arg(ventAngle) + zh(L"\u00b0"));
        servoHealthState->setText("");
        pumpState->setText(pumpEnabled ? "ON" : "OFF");
        pumpHealthState->setText("");
        queueState->setText(queuedAction == "none" || queuedAction == "keep" ? zh(L"\u7b49\u5f85\u6267\u884c") : shortActionText(queuedAction));

        decisionText->setText(compactDecisionText(diagnosis, level, stageIndex));
        actionText->setText(recommendationText(recommendation));
        actionSubText->setText(zh(L"\u4fdd\u6301\u5f53\u524d\u63a7\u5236\u7b56\u7565"));
        queuedActionText->setText(queuedAction == "none" || queuedAction == "keep" ? zh(L"\u6682\u65e0\u6307\u4ee4") : shortActionText(queuedAction));
        priorityText->setText(zh(L"\u4f18\u5148\u7ea7: ") + priorityTextCn(priority));

        updatingFromTelemetry = true;
        pumpSwitch->setChecked(pumpCommandPending && pumpTarget >= 0 ? pumpTarget != 0 : pumpEnabled);
        if (!motorSlider->isSliderDown()) {
            motorSlider->setValue(motorCommandPending ? motorTarget : int(motorPwm / 10.0) * 10);
        }
        if (!servoSlider->isSliderDown()) {
            servoSlider->setValue(servoCommandPending ? servoTarget : ventAngle);
        }
        updatingFromTelemetry = false;

        if (alarm != "none" || fault != "none") {
            addEvent(level, alarm, eventAction);
        }
    }

    int stageIndexFromTelemetry(const QJsonObject &obj) const
    {
        const QStringList numericKeys = {"stage_index", "stage_id", "phase_index"};
        for (const QString &key : numericKeys) {
            if (obj.contains(key)) {
                int index = obj.value(key).toInt(0);
                if (index >= 1 && index <= 4) {
                    return index - 1;
                }
                return qBound(0, index, 3);
            }
        }

        const QStringList textKeys = {"current_stage", "stage", "phase", "fermentation_stage"};
        QString value;
        for (const QString &key : textKeys) {
            value = obj.value(key).toString().trimmed().toLower();
            if (!value.isEmpty()) {
                break;
            }
        }

        if (value.contains("start") || value.contains("lag") || value.contains(zh(L"\u542f\u52a8"))) {
            return 0;
        }
        if (value.contains("growth") || value.contains("log") || value.contains("exponential") ||
            value.contains(zh(L"\u6307\u6570"))) {
            return 1;
        }
        if (value.contains("stable") || value.contains("stationary") || value.contains(zh(L"\u7a33\u5b9a"))) {
            return 2;
        }
        if (value.contains("decline") || value.contains("decay") || value.contains(zh(L"\u8870\u9000"))) {
            return 3;
        }

        return 0;
    }

    void setStage(int current)
    {
        current = qBound(0, current, 3);
        for (int i = 0; i < 4; ++i) {
            const bool done = i < current;
            const bool active = i == current;
            const QColor titleColor = active ? QColor(38, 243, 209) :
                                      done ? QColor(112, 230, 87) : QColor(180, 220, 235);
            const QColor stateColor = active ? QColor(38, 243, 209) :
                                      done ? QColor(112, 230, 87) : QColor(115, 160, 180);
            if (stageTitles[i]) {
                stageTitles[i]->setStyleSheet(QString("color: %1; background: transparent; font-weight: %2;")
                                                  .arg(styleColor(titleColor))
                                                  .arg(active ? 700 : 500));
            }
            if (stageIndicators[i]) {
                stageIndicators[i]->setText(active ? zh(L"\u25cf") : (done ? zh(L"\u221a") : zh(L"\u25cb")));
                stageIndicators[i]->setStyleSheet(QString("color: %1; background: transparent; font-weight: 700;").arg(styleColor(stateColor)));
            }
        }
    }

    QString compactDecisionText(const QString &raw, const QString &level, int stageIndex) const
    {
        QString text = raw.trimmed();
        if (text.isEmpty() || text == "normal" || text == "none") {
            const QStringList names = {zh(L"\u542f\u52a8\u671f"), zh(L"\u6307\u6570\u671f"),
                                       zh(L"\u7a33\u5b9a\u671f"), zh(L"\u8870\u9000\u671f")};
            text = names.value(qBound(0, stageIndex, 3));
        }
        if (level != "normal" && level != "none" && !text.contains(level)) {
            text = level + "\n" + text;
        }
        if (text.size() > 18) {
            text = text.left(18);
        }
        return text;
    }

    int motorTargetFromAction(const QString &raw, int fallback) const
    {
        QString text = raw.trimmed();
        if (text == "motor_stop") {
            return 0;
        }
        if (text.startsWith("motor_pwm_")) {
            bool ok = false;
            int value = text.mid(QString("motor_pwm_").size()).toInt(&ok);
            return ok ? qBound(0, value, 100) : fallback;
        }
        return fallback;
    }

    int servoTargetFromAction(const QString &raw, int fallback) const
    {
        QString text = raw.trimmed();
        if (text == "vent_close") {
            return 0;
        }
        if (text == "vent_mid") {
            return 45;
        }
        if (text == "vent_open") {
            return 90;
        }
        if (text.startsWith("vent_angle_")) {
            bool ok = false;
            int value = text.mid(QString("vent_angle_").size()).toInt(&ok);
            return ok ? qBound(0, value, 180) : fallback;
        }
        return fallback;
    }

    int pumpTargetFromAction(const QString &raw) const
    {
        QString text = raw.trimmed();
        if (text == "pump_water_on") {
            return 1;
        }
        if (text == "pump_water_off") {
            return 0;
        }
        return -1;
    }

    bool actionMatchesFeedback(const QString &raw, double motorPwm, int ventAngle, bool pumpEnabled) const
    {
        QString text = raw.trimmed();
        if (text.isEmpty() || text == "none" || text == "keep" || text == "normal") {
            return false;
        }
        if (text == "motor_stop" || text.startsWith("motor_pwm_")) {
            return qAbs(motorTargetFromAction(text, -999) - int(motorPwm + 0.5)) <= 1;
        }
        if (text.startsWith("vent_")) {
            return qAbs(servoTargetFromAction(text, -999) - ventAngle) <= 1;
        }
        if (text.startsWith("pump_water_")) {
            const int target = pumpTargetFromAction(text);
            return target >= 0 && (pumpEnabled ? 1 : 0) == target;
        }
        return false;
    }

    QString shortActionText(const QString &raw) const
    {
        QString text = raw.trimmed();
        if (text.isEmpty() || text == "none" || text == "keep" || text == "normal") {
            return zh(L"\u4fdd\u6301");
        }
        if (text.startsWith("motor_pwm_")) {
            return zh(L"\u6405\u62cc ") + text.mid(QString("motor_pwm_").size()) + "%";
        }
        if (text == "motor_stop") {
            return zh(L"\u505c\u6b62\u6405\u62cc");
        }
        if (text == "pump_water_on") {
            return zh(L"\u6c34\u6cf5 ON");
        }
        if (text == "pump_water_off") {
            return zh(L"\u6c34\u6cf5 OFF");
        }
        if (text.startsWith("vent_angle_")) {
            return zh(L"\u8235\u673a ") + text.mid(QString("vent_angle_").size()) + zh(L"\u00b0");
        }
        return text.size() > 16 ? text.left(16) : text;
    }

    QString recommendationText(const QString &raw) const
    {
        QString text = raw.trimmed();
        if (text.isEmpty() || text == "none" || text == "keep" || text == "normal") {
            return zh(L"\u7ef4\u6301\u4e2d\u901f\u6405\u62cc\n\u4fdd\u6301\u901a\u6c14");
        }
        if (text.startsWith("motor_pwm_")) {
            return shortActionText(text) + "\n" + zh(L"\u4fdd\u6301\u901a\u6c14");
        }
        return text.size() > 22 ? text.left(22) : text;
    }

    QString priorityTextCn(const QString &raw) const
    {
        QString text = raw.trimmed().toLower();
        if (text == "high" || text == "urgent" || text == zh(L"\u9ad8")) {
            return zh(L"\u9ad8");
        }
        if (text == "low" || text == zh(L"\u4f4e")) {
            return zh(L"\u4f4e");
        }
        if (text == "medium" || text == "mid" || text == zh(L"\u4e2d")) {
            return zh(L"\u4e2d");
        }
        return raw.isEmpty() ? zh(L"\u4e2d") : raw.left(4);
    }

    void setOnline(bool online, const QString &detail)
    {
        const QString text = online ? zh(L"\u5728\u7ebf") : zh(L"\u79bb\u7ebf");
        const QColor color = online ? QColor(112, 230, 87) : QColor(255, 176, 42);
        const QStringList details = online
            ? QStringList{zh(L"\u91c7\u96c6\u4e2d"), zh(L"\u4e0a\u4f20\u4e2d"), zh(L"\u5df2\u7f13\u5b58"), zh(L"\u5f85\u8c03\u7528"), zh(L"\u53ef\u4e0b\u53d1")}
            : QStringList{zh(L"\u65e0\u6570\u636e"), zh(L"\u65e0\u8fde\u63a5"), zh(L"\u6682\u505c"), zh(L"\u6682\u505c"), zh(L"\u6682\u505c")};
        const QColor detailColor = online ? QColor(105, 205, 230) : QColor(255, 176, 42);

        for (int i = 0; i < 5; ++i) {
            if (nodeRows[i]) {
                nodeRows[i]->setText(text);
                nodeRows[i]->setStyleSheet(QString("color: %1; background: transparent;").arg(styleColor(color)));
            }
            if (nodeDetailRows[i]) {
                nodeDetailRows[i]->setText(details.value(i, "--"));
                nodeDetailRows[i]->setStyleSheet(QString("color: %1; background: transparent;").arg(styleColor(detailColor)));
            }
        }
        connectionState->setText(QString("%1: %2").arg(zh(L"\u63a5\u53e3")).arg(detail));
        connectionState->setStyleSheet(QString("color: %1; background: transparent;").arg(
            styleColor(online ? QColor(155, 230, 245) : QColor(255, 176, 42))));
    }

    void addEvent(const QString &level, const QString &reason, const QString &action)
    {
        if (eventTable->rowCount() > 0) {
            const QString lastReason = eventTable->item(0, 2) ? eventTable->item(0, 2)->text() : "";
            if (lastReason == reason) {
                return;
            }
        }
        eventTable->insertRow(0);
        eventTable->setRowHeight(0, 28);
        const QString now = QDateTime::currentDateTime().toString("HH:mm:ss");
        const QStringList values = {
            now,
            alarmLevelText(level),
            reason == "none" ? zh(L"\u8bbe\u5907\u5f02\u5e38") : reason.left(12),
            action == "none" || action == "keep" ? zh(L"\u5df2\u8bb0\u5f55") : shortActionText(action),
            zh(L"\u5df2\u5904\u7406")
        };
        for (int col = 0; col < values.size(); ++col) {
            QTableWidgetItem *item = new QTableWidgetItem(values[col]);
            item->setTextAlignment(Qt::AlignCenter);
            item->setForeground(QColor(210, 245, 255));
            eventTable->setItem(0, col, item);
        }
        while (eventTable->rowCount() > 4) {
            eventTable->removeRow(eventTable->rowCount() - 1);
        }
    }

    void appendLog(const QString &line)
    {
        const QString now = QDateTime::currentDateTime().toString("HH:mm:ss");
        feedbackLog->appendPlainText(QString("[%1] %2").arg(now, line));
        feedbackLog->verticalScrollBar()->setValue(feedbackLog->verticalScrollBar()->maximum());
    }

    QString alarmLevelText(const QString &level) const
    {
        if (level == "critical" || level == "severe") {
            return zh(L"\u4e25\u91cd");
        }
        if (level == "warning" || level == "warn") {
            return zh(L"\u8b66\u544a");
        }
        if (level == "normal" || level == "none") {
            return zh(L"\u8bb0\u5f55");
        }
        return level.left(4);
    }
};

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QString baseUrl = "http://127.0.0.1:8080";
    if (app.arguments().size() >= 2) {
        baseUrl = app.arguments().at(1);
    }

    ControlWindow window(baseUrl);
    window.show();
    return app.exec();
}
