/*
  ==============================================================================

    BaseComponent.cpp
    Created: 7 Nov 2025 11:56:15pm
    Author:  Jonathan

  ==============================================================================
*/

#include "BaseComponent.h"
#include "../layout/WFlexLayout.h"

class WBaseComponentLayout : public WParentLayout {
public:
	
	WBaseComponentLayout() {}

	void applyLayout(const Rectangle<int>& bParent, const Array<Component*>& children) override {
		const auto c = getValidChildren(children);
		if (c.empty())
			return;
		c[0]->setBounds(bParent);
	}

private:
};



BaseComponent::BaseComponent()
	: _asyncResizer(this)
	// , _parentLayout(new WFlexLayout(WFlexLayout::Options::horizontal_group())) //WBaseComponentLayout
	, _preferredSizeListener([&]() { triggerAsyncResize(); })
	{

	getPreferredSize().addListener(&_preferredSizeListener);
}

BaseComponent::~BaseComponent() {
	clearOwnedChildren();
}

void BaseComponent::resized() {
	applyLayout();
}

WLayout& BaseComponent::getLayout() {
	return _wlayout;
}

const WLayout& BaseComponent::getLayout() const {
	return _wlayout;
}

void BaseComponent::setLayout(const WLayout& layout) { _wlayout = layout; }

WPreferredSize& BaseComponent::getPreferredSize() { return _wPreferredSize; }

const WPreferredSize& BaseComponent::getPreferredSize() const { return _wPreferredSize; }

void BaseComponent::setPreferredSize(const WPreferredSize& psize) { _wPreferredSize = psize; }

WParentLayout* BaseComponent::getParentLayout() { return _parentLayout.get(); }

const WParentLayout* BaseComponent::getParentLayout() const { return _parentLayout.get(); }

void BaseComponent::setParentLayout(WParentLayout* layout) { return _parentLayout.reset(layout); }

BorderSize<int> BaseComponent::getBorders() const { return _borders; }

void BaseComponent::setBorders(const BorderSize<int>& b) { _borders = b; }

void BaseComponent::setBorders(int size) {
	_borders = BorderSize<int>(size);
}

void BaseComponent::applyLayout() {
	const auto bParent = _borders.subtractedFrom(getLocalBounds());
	if (_parentLayout) 
		_parentLayout->applyLayout(bParent, getChildren());
	else {
		WParentLayout l;
		l.applyLayout(bParent, getChildren());
	}
}

void BaseComponent::triggerAsyncResize() {
	_asyncResizer.triggerAsyncResize();
}

void BaseComponent::setEditor(bool isEditor) {
	setInterceptsMouseClicks(isEditor, true);
	setWantsKeyboardFocus(isEditor);
}

void BaseComponent::addOwnedChildren(Component* c) {
	_ownedChildren.emplace_back(c);
}

void BaseComponent::removeOwnedChildren(Component* c) {
	for (int i = _ownedChildren.size() - 1; i >= 0; i--) {
		if (_ownedChildren[i].get() == c) 
			_ownedChildren.erase(_ownedChildren.begin() + i);
	}
}

void BaseComponent::clearOwnedChildren() {
	_ownedChildren.clear();
}

void BaseComponent::ownAndMakeVisible(Component* c) {
	addAndMakeVisible(c);
	addOwnedChildren(c);
}







