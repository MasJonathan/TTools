/*
  ==============================================================================

	WFlexLayout.cpp
	Created: 8 Nov 2025 12:53:22am
	Author:  Jonathan

  ==============================================================================
*/

#include "WFlexLayout.h"

WFlexLayout::WFlexLayout(const Options& opts) : options(opts) {}

void WFlexLayout::setOptions(const Options& opts) { options = opts; }

const WFlexLayout::Options& WFlexLayout::getOptions() const { return options; }

void WFlexLayout::applyLayout(const Rectangle<int>& bParent, const Array<Component*>& children) {
	std::vector<BaseComponent*> validChildren;
	int totalPreferredMain = 0;
	int totalFlexible = 0;

	for (auto* c : children) {
		if (auto* bc = dynamic_cast<BaseComponent*>(c)) {
			if (!bc->getPreferredSize().getIgnoreLayout()) {
				validChildren.push_back(bc);
				if (options.direction == Direction::Row)
					totalPreferredMain += bc->getPreferredSize().getPreferredWidth();
				else
					totalPreferredMain += bc->getPreferredSize().getPreferredHeight();

				totalFlexible += (options.direction == Direction::Row)
					? bc->getPreferredSize().getFlexibleWidth()
					: bc->getPreferredSize().getFlexibleHeight();
			}
		}
	}

	if (validChildren.empty()) return;

	int mainSize = (options.direction == Direction::Row) ? bParent.getWidth() : bParent.getHeight();
	int crossSize = (options.direction == Direction::Row) ? bParent.getHeight() : bParent.getWidth();
	int remaining = mainSize - totalPreferredMain - ((int)validChildren.size() - 1) * options.spacing;
	int mainPos = (options.direction == Direction::Row) ? bParent.getX() : bParent.getY();
	int crossPos = (options.direction == Direction::Row) ? bParent.getY() : bParent.getX();

	int space = 0;
	bool stretchItems = false;

	switch (options.justify) {
	case JustifyContent::Center:
		mainPos += remaining / 2;
		break;
	case JustifyContent::FlexEnd:
		mainPos += remaining;
		break;
	case JustifyContent::SpaceBetween:
		space = validChildren.size() > 1 ? remaining / (validChildren.size() - 1) : 0;
		break;
	case JustifyContent::SpaceAround:
		space = validChildren.size() > 0 ? remaining / validChildren.size() : 0;
		mainPos += space / 2;
		break;
	case JustifyContent::SpaceEvenly:
		space = validChildren.size() > 0 ? remaining / (validChildren.size() + 1) : 0;
		mainPos += space;
		break;
	case JustifyContent::Stretch:
		stretchItems = true;
		break;
	default:
		break;
	}

	int stretchSize = 0;
	if (stretchItems && validChildren.size() > 0) {
		stretchSize = (mainSize - ((int)validChildren.size() - 1) * options.spacing) / (int)validChildren.size();
	}

	int currentLineCrossSize = 0;
	std::vector<BaseComponent*> lineChildren;
	auto flushLine = [&](int startMainPos) {
		int localMainPos = startMainPos;
		for (auto* bc : lineChildren) {
			auto& pref = bc->getPreferredSize();

			int prefMain = (options.direction == Direction::Row)
				? pref.getPreferredWidth()
				: pref.getPreferredHeight();
			int flex = (options.direction == Direction::Row)
				? pref.getFlexibleWidth()
				: pref.getFlexibleHeight();
			int minMain = (options.direction == Direction::Row)
				? pref.getMinWidth()
				: pref.getMinHeight();
			int prefCross = (options.direction == Direction::Row)
				? pref.getPreferredHeight()
				: pref.getPreferredWidth();

			float flexFactor = (totalFlexible > 0 && flex > 0)
				? static_cast<float>(flex) / totalFlexible
				: 0.0f;

			int extraMain = stretchItems ? 0 : static_cast<int>(std::round(flexFactor * remaining));

			int sizeMain = stretchItems
				? jmax(minMain, stretchSize)
				: jmax(minMain, prefMain + extraMain);

			int posCross = 0;
			int sizeCross = prefCross;
			switch (options.align) {
			case AlignItems::Stretch: sizeCross = currentLineCrossSize; break;
			case AlignItems::Center: posCross = (currentLineCrossSize - sizeCross) / 2; break;
			case AlignItems::FlexEnd: posCross = currentLineCrossSize - sizeCross; break;
			default: break;
			}

			Rectangle<int> childBounds;
			if (options.direction == Direction::Row) {
				childBounds = Rectangle<int>(localMainPos, crossPos + posCross, sizeMain, sizeCross);
				localMainPos += sizeMain + options.spacing;
			}
			else {
				childBounds = Rectangle<int>(crossPos + posCross, localMainPos, sizeCross, sizeMain);
				localMainPos += sizeMain + options.spacing;
			}
			bc->setBounds(childBounds);
		}
		lineChildren.clear();
	};

	int usedMain = 0;
	for (auto* bc : validChildren) {
		auto& pref = bc->getPreferredSize();
		int childMainSize = (options.direction == Direction::Row)
			? pref.getPreferredWidth()
			: pref.getPreferredHeight();
		if (options.wrap == FlexWrap::Wrap && usedMain + childMainSize > mainSize && !lineChildren.empty()) {
			flushLine(mainPos);
			if (options.direction == Direction::Row)
				crossPos += currentLineCrossSize + options.spacing;
			else
				crossPos += currentLineCrossSize + options.spacing;
			mainPos = (options.direction == Direction::Row) ? bParent.getX() : bParent.getY();
			usedMain = 0;
			currentLineCrossSize = 0;
		}
		lineChildren.push_back(bc);
		int childCrossSize = (options.direction == Direction::Row)
			? pref.getPreferredHeight()
			: pref.getPreferredWidth();
		currentLineCrossSize = jmax(currentLineCrossSize, childCrossSize);
		usedMain += childMainSize + options.spacing;
	}
	if (!lineChildren.empty()) flushLine(mainPos);
}
