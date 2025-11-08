/*
  ==============================================================================

	WLayout.h
	Created: 8 Nov 2025 12:00:00am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "JuceHeader.h"

class BaseComponent;

class WLayout {
public:
	WLayout() {
		_pivot = { 0.5f, 0.5f };
		_offset = { 0, 0, 0, 0 };
		_borders = { 0, 0, 0, 0 };
		_anchors = { 0.0f, 0.0f, 1.0f, 1.0f };
	}

	Rectangle<int> LayoutBounds(const Rectangle<int> bParent) {
		bool anchorStretchX = _anchors.getLeft() != _anchors.getRight();
		bool anchorStretchY = _anchors.getTop() != _anchors.getBottom();

		float parentX = static_cast<float>(bParent.getX());
		float parentY = static_cast<float>(bParent.getY());
		float parentW = static_cast<float>(bParent.getWidth());
		float parentH = static_cast<float>(bParent.getHeight());

		float xMin = parentX + _anchors.getLeft() * parentW + _offset.getX();
		float yMin = parentY + _anchors.getTop() * parentH + _offset.getY();
		float xMax = parentX + _anchors.getRight() * parentW - _offset.getWidth();
		float yMax = parentY + _anchors.getBottom() * parentH - _offset.getHeight();

		float w, h, x, y;

		if (anchorStretchX) {
			w = xMax - xMin;
			x = xMin + (0.5f - _pivot.x) * w;
		}
		else {
			w = _offset.getWidth();
			x = xMin - _pivot.x * w;
		}

		if (anchorStretchY) {
			h = yMax - yMin;
			y = yMin + (0.5f - _pivot.y) * h;
		}
		else {
			h = _offset.getHeight();
			y = yMin - _pivot.y * h;
		}

		return Rectangle<int>(static_cast<int>(std::round(x)),
			static_cast<int>(std::round(y)),
			static_cast<int>(std::round(w)),
			static_cast<int>(std::round(h)));
	}


	// Pivot
	WLayout& setPivot(Point<float> p) { _pivot = p; return *this; }
	Point<float> getPivot() const { return _pivot; }
	WLayout& setPivotX(float x) { _pivot.x = x; return *this; }
	float getPivotX() const { return _pivot.x; }
	WLayout& setPivotY(float y) { _pivot.y = y; return *this; }
	float getPivotY() const { return _pivot.y; }

	// Offset
	WLayout& setOffset(Rectangle<float> o) { _offset = o; return *this; }
	Rectangle<float> getOffset() const { return _offset; }
	WLayout& setX(float v) { _offset.setX(v); return *this; }
	float getX() const { return _offset.getX(); }
	WLayout& setY(float v) { _offset.setY(v); return *this; }
	float getY() const { return _offset.getY(); }
	WLayout& setWidth(float v) { _offset.setWidth(v); return *this; }
	float getWidth() const { return _offset.getWidth(); }
	WLayout& setHeight(float v) { _offset.setHeight(v); return *this; }
	float getHeight() const { return _offset.getHeight(); }

	// Borders
	WLayout& setBorders(BorderSize<float> b) { _borders = b; return *this; }
	BorderSize<float> getBorders() const { return _borders; }
	WLayout& setBorderLeft(float v) { _borders.setLeft(v); return *this; }
	float getBorderLeft() const { return _borders.getLeft(); }
	WLayout& setBorderRight(float v) { _borders.setRight(v); return *this; }
	float getBorderRight() const { return _borders.getRight(); }
	WLayout& setBorderTop(float v) { _borders.setTop(v); return *this; }
	float getBorderTop() const { return _borders.getTop(); }
	WLayout& setBorderBottom(float v) { _borders.setBottom(v); return *this; }
	float getBorderBottom() const { return _borders.getBottom(); }

	// Anchors
	WLayout& setAnchors(BorderSize<float> a) { _anchors = a; return *this; }
	BorderSize<float> getAnchors() const { return _anchors; }
	WLayout& setAnchorLeft(float v) { _anchors.setLeft(v); return *this; }
	float getAnchorLeft() const { return _anchors.getLeft(); }
	WLayout& setAnchorRight(float v) { _anchors.setRight(v); return *this; }
	float getAnchorRight() const { return _anchors.getRight(); }
	WLayout& setAnchorTop(float v) { _anchors.setTop(v); return *this; }
	float getAnchorTop() const { return _anchors.getTop(); }
	WLayout& setAnchorBottom(float v) { _anchors.setBottom(v); return *this; }
	float getAnchorBottom() const { return _anchors.getBottom(); }

private:
	Point<float> _pivot;
	Rectangle<float> _offset;
	BorderSize<float> _borders;
	BorderSize<float> _anchors;
};

class WPreferredSize {
public:
	struct Listener {
		virtual void onPreferredSizeChange() = 0;
		virtual ~Listener() = default;
	};
	struct ListenerLambda : public Listener {
		std::function<void()> f;

		ListenerLambda(std::function<void()> f) : f(f) {}

		void onPreferredSizeChange() override {
			if (f) f();
		}
	};

	WPreferredSize() = default;

	// -------- GETTERS / SETTERS --------
	bool getIgnoreLayout() const { return ignoreLayout; }
	WPreferredSize& setIgnoreLayout(bool v, bool notify=true) {
		ignoreLayout = v;
		if (notify) notifyListeners();
		return *this;
	}

	int getMinWidth() const { return minWidth; }
	WPreferredSize& setMinWidth(int v, bool notify = true) {
		if (minWidth != v) {
			minWidth = v;
			if (notify) notifyListeners();
		}
		return *this;
	}

	int getMinHeight() const { return minHeight; }
	WPreferredSize& setMinHeight(int v, bool notify = true) {
		if (minHeight != v) {
			minHeight = v;
			if (notify) notifyListeners();
		}
		return *this;
	}

	Point<int> getMinSize() const { return { minWidth, minHeight }; }
	WPreferredSize& setMinSize(int w, int h, bool notify = true) {
		minWidth = w; minHeight = h;
		if (notify) notifyListeners();
		return *this;
	}

	int getPreferredWidth() const { return preferredWidth; }
	WPreferredSize& setPreferredWidth(int v, bool notify = true) {
		if (preferredWidth != v) {
			preferredWidth = v;
			if (notify) notifyListeners();
		}
		return *this;
	}

	int getPreferredHeight() const { return preferredHeight; }
	WPreferredSize& setPreferredHeight(int v, bool notify = true) {
		if (preferredHeight != v) {
			preferredHeight = v;
			if (notify) notifyListeners();
		}
		return *this;
	}

	Point<int> getPreferredSize() const { return { preferredWidth, preferredHeight }; }
	WPreferredSize& setPreferredSize(int w, int h, bool notify = true) {
		preferredWidth = w; preferredHeight = h;
		if (notify) notifyListeners();
		return *this;
	}

	int getFlexibleWidth() const { return flexibleWidth; }
	WPreferredSize& setFlexibleWidth(int v, bool notify = true) {
		if (flexibleWidth != v) {
			flexibleWidth = v;
			if (notify) notifyListeners();
		}
		return *this;
	}

	int getFlexibleHeight() const { return flexibleHeight; }
	WPreferredSize& setFlexibleHeight(int v, bool notify = true) {
		if (flexibleHeight != v) {
			flexibleHeight = v;
			if (notify) notifyListeners();
		}
		return *this;
	}

	Point<int> getFlexibleSize() const { return { flexibleWidth, flexibleHeight }; }
	WPreferredSize& setFlexibleSize(int w, int h, bool notify = true) {
		flexibleWidth = w; flexibleHeight = h;
		if (notify) notifyListeners();
		return *this;
	}


	// -------- LISTENER MANAGEMENT --------
	WPreferredSize& addListener(Listener* l) {
		if (l && std::find(_listeners.begin(), _listeners.end(), l) == _listeners.end())
			_listeners.push_back(l);
		return *this;
	}

	WPreferredSize& removeListener(Listener* l) {
		_listeners.erase(std::remove(_listeners.begin(), _listeners.end(), l), _listeners.end());
		return *this;
	}

private:
	bool ignoreLayout = false;
	int minWidth = 0;
	int minHeight = 0;
	int preferredWidth = 0;
	int preferredHeight = 0;
	int flexibleWidth = 0;
	int flexibleHeight = 0;
	std::vector<Listener*> _listeners;

	void notifyListeners() {
		for (auto* l : _listeners)
			if (l) l->onPreferredSizeChange();
	}
};

class WParentLayout {
public:
	virtual void applyLayout(const Rectangle<int>& bParent, const Array<Component*>& children) = 0;

	std::vector<BaseComponent*> getValidChildren(const Array<Component*>& children);
};

